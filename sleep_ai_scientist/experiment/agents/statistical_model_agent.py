from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, r2_score, roc_auc_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_score, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.svm import SVC, SVR
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

try:  # pragma: no cover - availability is environment-specific.
    from xgboost import XGBClassifier, XGBRegressor
except Exception:  # pragma: no cover
    XGBClassifier = None
    XGBRegressor = None

try:  # pragma: no cover - availability is environment-specific.
    from lightgbm import LGBMClassifier, LGBMRegressor
except Exception:  # pragma: no cover
    LGBMClassifier = None
    LGBMRegressor = None

from sleep_ai_scientist.common.io import write_json
from sleep_ai_scientist.experiment.agents.analysis_templates import (
    load_analysis_table,
    run_negative_controls,
    run_primary_tests,
    run_robustness_checks,
)
from sleep_ai_scientist.experiment.agents.llm_adapter import build_experiment_llm, load_prompt
from sleep_ai_scientist.experiment.model_selection import select_primary_model
from sleep_ai_scientist.schemas.experiment import (
    ExperimentPlan,
    MLAgentResult,
    NegativeControlResult,
    RobustnessCheckResult,
    StatsAgentResult,
)


class StatisticalModelAgent:
    """Uses LLM model judgment, then executes controlled statistical templates."""

    def __init__(self, config: dict[str, Any], *, output_dir: str | Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.llm = build_experiment_llm(
            config.get("llm", {}),
            task_name="StatisticalModelAgent: select AnalysisDSL and controlled templates",
        )

    def run(
        self,
        plan: ExperimentPlan,
        *,
        bootstrap_iterations: int,
    ) -> tuple[StatsAgentResult, MLAgentResult | None, list[RobustnessCheckResult], list[NegativeControlResult], dict[str, Any]]:
        model_review = self._llm_select_model(plan) if self.llm else self._llm_required_model(plan)
        model_selection = self._select_primary_template(plan, model_review)
        primary_template = str(model_selection["primary_template"])
        self._log_model_selection(model_selection)
        tests = run_primary_tests(plan, primary_template=primary_template)
        robustness = run_robustness_checks(plan, tests, iterations=bootstrap_iterations)
        negative_controls = run_negative_controls(plan)
        passed = sum(1 for test in tests if test.passed)
        stats_result = StatsAgentResult(
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            tests=tests,
            summary=f"{passed}/{len(tests)} primary statistical tests passed p<0.05.",
        )
        ml_enabled_by_policy = bool(model_selection.get("run_ml", False))
        ml_result = self._run_ml_templates(plan) if ml_enabled_by_policy else None
        trace = {
            "model_review": model_review,
            "model_selection_policy": model_selection,
            "controlled_templates": {
                "primary": primary_template,
                "robustness": "bootstrap_spearman_ci",
                "negative_control": "spearman_negative_control",
                "ml": list(self.config.get("ml_models", ["decision_tree"])),
                "ml_enabled_by_policy": ml_enabled_by_policy,
            },
        }
        write_json(
            self.output_dir / f"{plan.plan_id}.statistical_model.json",
            {
                **trace,
                "stats_result": stats_result.model_dump(),
                "ml_result": ml_result.model_dump() if ml_result else None,
                "robustness_results": [item.model_dump() for item in robustness],
                "negative_control_results": [item.model_dump() for item in negative_controls],
            },
        )
        return stats_result, ml_result, robustness, negative_controls, trace

    def _llm_select_model(self, plan: ExperimentPlan) -> dict[str, Any]:
        system, user, max_tokens = load_prompt(
            "statistical_model",
            "select_model",
            {"execution_plan_json": json.dumps(plan.model_dump(), ensure_ascii=False, indent=2)},
        )
        return self.llm.call_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=float(self.config.get("llm", {}).get("temperature", 0.1)),
        )

    def _llm_required_model(self, plan: ExperimentPlan) -> dict[str, Any]:
        return {
            "status": "requires_llm_review",
            "reason": "Experiment LLM is disabled; controlled templates will still execute but model-choice judgment is absent.",
        }

    def _select_primary_template(self, plan: ExperimentPlan, model_review: dict[str, Any]) -> dict[str, Any]:
        configured = str(self.config.get("primary_template", "") or "").strip()
        configured_ml = [str(item) for item in self.config.get("ml_models", ["decision_tree"])]
        return select_primary_model(
            plan,
            configured_template=configured or "auto",
            model_review=model_review,
            configured_ml_models=configured_ml,
        )

    def _log_model_selection(self, selection: dict[str, Any]) -> None:
        if not bool(self.config.get("verbose", False)):
            return
        print(
            "[experiment:model_selection] "
            f"plan={selection.get('plan_id')} "
            f"primary={selection.get('primary_template')} "
            f"source={selection.get('source')} "
            f"ml={'enabled' if selection.get('run_ml') else 'disabled'} "
            f"n={selection.get('n_rows', '')} "
            f"covariates={','.join(selection.get('covariates', []) or []) or 'none'} "
            f"reason={selection.get('reason')}",
            flush=True,
        )

    def _run_ml_templates(self, plan: ExperimentPlan) -> MLAgentResult:
        outcome = plan.outcomes[0] if plan.outcomes else ""
        features = list(plan.predictors)
        table = load_analysis_table(plan, {outcome, *features})
        clean = _clean_ml_table(table, features, outcome)
        if clean.empty or len(clean) < 4:
            return self._ml_placeholder(plan, notes="Insufficient non-missing observations for ML templates.")

        task_type = _infer_ml_task_type(clean[outcome])
        configured = [str(item) for item in self.config.get("ml_models", ["decision_tree"])]
        supported = _expand_ml_models(configured, task_type)
        if not supported:
            return self._ml_placeholder(plan, notes="No supported ML templates were configured.")

        x = clean[features]
        y = clean[outcome]
        cv_folds = max(2, min(int(self.config.get("ml_cv_folds", 5)), len(clean)))
        if task_type == "classification":
            min_class_count = int(y.value_counts().min()) if not y.empty else 0
            cv_folds = max(2, min(cv_folds, min_class_count)) if min_class_count >= 2 else 0
        models: dict[str, Any] = {}
        scores: list[float] = []
        importances: dict[str, list[float]] = {feature: [] for feature in features}
        for model_name in supported:
            estimator = _build_ml_estimator(model_name)
            if estimator is None:
                models[model_name] = {"error": "Dependency not installed."}
                continue
            if cv_folds < 2:
                models[model_name] = {"error": "Insufficient class counts for cross-validation."}
                continue
            cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42) if task_type == "classification" else KFold(n_splits=cv_folds, shuffle=True, random_state=42)
            scoring = "roc_auc" if task_type == "classification" else "r2"
            try:
                cv_scores = cross_val_score(estimator, x, y, cv=cv, scoring=scoring)
                predictions = cross_val_predict(estimator, x, y, cv=cv)
                probabilities = _positive_class_probabilities(estimator, x, y, cv) if task_type == "classification" else None
                estimator.fit(x, y)
                importance = _model_feature_importance(estimator, features, model_name)
                scores.extend(float(value) for value in cv_scores)
                for feature, value in importance.items():
                    importances[feature].append(value)
                model_payload = {
                    "score_name": scoring,
                    "score_mean": float(pd.Series(cv_scores).mean()),
                    "score_std": float(pd.Series(cv_scores).std(ddof=0)),
                    "feature_importance": importance,
                    "predictions": [float(value) for value in predictions],
                    "observed": [float(value) for value in y],
                }
                if task_type == "classification":
                    model_payload.update(
                        {
                            "accuracy": float(accuracy_score(y, predictions)),
                            "confusion_matrix": confusion_matrix(y, predictions, labels=sorted(y.unique())).tolist(),
                            "classes": [float(value) for value in sorted(y.unique())],
                            "probabilities": [float(value) for value in probabilities] if probabilities is not None else [],
                        }
                    )
                    if probabilities is not None and len(set(y)) == 2:
                        model_payload["roc_auc"] = float(roc_auc_score(y, probabilities))
                else:
                    model_payload["r2"] = float(r2_score(y, predictions))
                if model_name == "logistic_regression":
                    coefficients = getattr(estimator, "named_steps", {}).get("logisticregression", estimator)
                    model_payload["coefficients"] = _linear_coefficients(coefficients, features)
                models[model_name] = model_payload
            except Exception as exc:
                models[model_name] = {"error": f"{type(exc).__name__}: {exc}"}

        mean_importance = {
            feature: float(pd.Series(values).mean()) if values else 0.0
            for feature, values in importances.items()
        }
        return MLAgentResult(
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            outcome=outcome,
            features=features,
            n=len(clean),
            model_type=",".join(supported),
            cv_folds=cv_folds,
            score_name="roc_auc" if task_type == "classification" else "r2",
            score_mean=float(pd.Series(scores).mean()) if scores else None,
            score_std=float(pd.Series(scores).std(ddof=0)) if scores else None,
            feature_importance=mean_importance,
            notes=f"Controlled ML templates for {task_type}.",
            metadata={"task_type": task_type, "models": models},
        )

    def _ml_placeholder(self, plan: ExperimentPlan, *, notes: str = "") -> MLAgentResult:
        return MLAgentResult(
            plan_id=plan.plan_id,
            hypothesis_id=plan.hypothesis_id,
            outcome=plan.outcomes[0] if plan.outcomes else "",
            features=list(plan.predictors),
            model_type="not_run",
            notes=notes or "ML execution is intentionally gated; statistical templates provide the primary test.",
        )


def _clean_ml_table(table: pd.DataFrame, features: list[str], outcome: str) -> pd.DataFrame:
    if table.empty or outcome not in table.columns or any(feature not in table.columns for feature in features):
        return pd.DataFrame(columns=[*features, outcome])
    clean = table[[*features, outcome]].copy()
    for column in [*features, outcome]:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    return clean.dropna(subset=[*features, outcome])


def _infer_ml_task_type(y: pd.Series) -> str:
    unique = sorted(pd.Series(y).dropna().unique())
    if len(unique) <= 2 and all(float(value).is_integer() for value in unique):
        return "classification"
    return "regression"


def _expand_ml_models(configured: list[str], task_type: str) -> list[str]:
    output: list[str] = []
    for name in configured:
        normalized = name.strip().lower()
        if not normalized:
            continue
        if normalized == "logistic_regression":
            if task_type == "classification":
                output.append("logistic_regression")
        elif normalized == "decision_tree":
            output.append("decision_tree_classifier" if task_type == "classification" else "decision_tree_regressor")
        elif normalized == "random_forest":
            output.append("random_forest_classifier" if task_type == "classification" else "random_forest_regressor")
        elif normalized == "svm":
            output.append("svm_classifier" if task_type == "classification" else "svm_regressor")
        elif normalized == "xgboost":
            output.append("xgboost_classifier" if task_type == "classification" else "xgboost_regressor")
        elif normalized == "lightgbm":
            output.append("lightgbm_classifier" if task_type == "classification" else "lightgbm_regressor")
        elif normalized.endswith("_classifier") and task_type == "classification":
            output.append(normalized)
        elif normalized.endswith("_regressor") and task_type == "regression":
            output.append(normalized)
    return list(dict.fromkeys(output))


def _build_ml_estimator(model_name: str) -> Any:
    if model_name == "logistic_regression":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, random_state=42, solver="liblinear"))
    if model_name == "decision_tree_classifier":
        return DecisionTreeClassifier(random_state=42, min_samples_leaf=1)
    if model_name == "random_forest_classifier":
        return RandomForestClassifier(n_estimators=100, random_state=42, min_samples_leaf=1)
    if model_name == "svm_classifier":
        return make_pipeline(StandardScaler(), SVC(kernel="rbf", probability=True, random_state=42))
    if model_name == "xgboost_classifier":
        if XGBClassifier is None:
            return None
        return XGBClassifier(n_estimators=50, max_depth=3, learning_rate=0.1, eval_metric="logloss", random_state=42)
    if model_name == "lightgbm_classifier":
        if LGBMClassifier is None:
            return None
        return LGBMClassifier(n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42, verbose=-1)
    if model_name == "random_forest_regressor":
        return RandomForestRegressor(n_estimators=100, random_state=42, min_samples_leaf=1)
    if model_name == "svm_regressor":
        return make_pipeline(StandardScaler(), SVR(kernel="rbf"))
    if model_name == "xgboost_regressor":
        if XGBRegressor is None:
            return None
        return XGBRegressor(n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42)
    if model_name == "lightgbm_regressor":
        if LGBMRegressor is None:
            return None
        return LGBMRegressor(n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42, verbose=-1)
    return DecisionTreeRegressor(random_state=42, min_samples_leaf=1)


def _model_feature_importance(estimator: Any, features: list[str], model_name: str) -> dict[str, float]:
    model = _last_pipeline_step(estimator)
    if hasattr(model, "feature_importances_"):
        return {feature: float(value) for feature, value in zip(features, model.feature_importances_, strict=False)}
    if hasattr(model, "coef_"):
        coefficients = pd.Series(model.coef_[0] if getattr(model.coef_, "ndim", 1) > 1 else model.coef_, index=features)
        absolute = coefficients.abs()
        total = float(absolute.sum())
        return {feature: float(value / total) if total else 0.0 for feature, value in absolute.items()}
    return {feature: 0.0 for feature in features}


def _last_pipeline_step(estimator: Any) -> Any:
    if hasattr(estimator, "steps") and estimator.steps:
        return estimator.steps[-1][1]
    return estimator


def _positive_class_probabilities(estimator: Any, x: pd.DataFrame, y: pd.Series, cv: Any) -> list[float] | None:
    if not hasattr(estimator, "predict_proba"):
        try:
            probabilities = cross_val_predict(estimator, x, y, cv=cv, method="decision_function")
            series = pd.Series(probabilities)
            min_value = float(series.min())
            max_value = float(series.max())
            if max_value == min_value:
                return [0.5 for _ in probabilities]
            return [float((value - min_value) / (max_value - min_value)) for value in probabilities]
        except Exception:
            return None
    try:
        probabilities = cross_val_predict(estimator, x, y, cv=cv, method="predict_proba")
        if getattr(probabilities, "ndim", 1) == 2 and probabilities.shape[1] >= 2:
            return [float(value) for value in probabilities[:, 1]]
    except Exception:
        return None
    return None


def _linear_coefficients(model: Any, features: list[str]) -> dict[str, float]:
    if not hasattr(model, "coef_"):
        return {}
    values = model.coef_[0] if getattr(model.coef_, "ndim", 1) > 1 else model.coef_
    return {feature: float(value) for feature, value in zip(features, values, strict=False)}
