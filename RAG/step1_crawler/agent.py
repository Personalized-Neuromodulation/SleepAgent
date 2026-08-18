import os
import logging
import re
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    import ollama  # 替代 openai
except ImportError:
    ollama = None

try:
    import yaml
except ImportError:
    yaml = None


def get_llm_setting(config, key, default, caster):
    try:
        value = (config or {}).get(key, default)
        if value in (None, ''):
            return default
        return caster(value)
    except Exception:
        return default


def classify_llm_error(error):
    text = str(error)
    lowered = text.lower()
    if 'timed out' in lowered or 'timeout' in lowered:
        return 'LLM timeout'
    if '403' in lowered or 'forbidden' in lowered:
        return 'LLM 403 forbidden'
    if '502' in lowered or 'bad gateway' in lowered:
        return 'LLM 502 bad gateway'
    if '503' in lowered or 'service unavailable' in lowered:
        return 'LLM service unavailable'
    if 'parse' in lowered or 'expecting value' in lowered:
        return 'LLM parse failed'
    if not text.strip():
        return 'LLM empty response'
    return f'LLM error: {text}'


class PaperAgent:
    """
    论文智能分析代理（基于本地 Ollama 模型）
    """

    def __init__(self, logger=None, config_path=None):
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        if not config_path:
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
        self.config = self._load_config(config_path)

        # Ollama 配置
        self.model = self.config.get('MAIN_LLM_MODEL', 'qwen3:latest')
        self.ollama_host = self.config.get('OLLAMA_HOST', 'http://localhost:11434')
        self.keep_alive = str(self.config.get('OLLAMA_KEEP_ALIVE', '-1')).strip()
        self.disable_thinking = bool(self.config.get('OLLAMA_DISABLE_THINKING', True))
        self.client = ollama.Client(host=self.ollama_host) if ollama is not None else None

        timeout_seconds = get_llm_setting(self.config, 'LLM_TIMEOUT_SECONDS', 120, float)
        max_retries = get_llm_setting(self.config, 'LLM_MAX_RETRIES', 3, int)
        self.timeout = timeout_seconds
        self.max_retries = max_retries

        self.batch_size = get_llm_setting(self.config, 'LLM_BATCH_SIZE', 1, int)
        self.retry_base_delay = get_llm_setting(self.config, 'LLM_RETRY_BASE_DELAY_SECONDS', 5, float)
        self.batch_delay = get_llm_setting(self.config, 'LLM_BATCH_DELAY_SECONDS', 1, float)
        self.max_title_chars = get_llm_setting(self.config, 'LLM_MAX_TITLE_CHARS', 500, int)
        # Keep the config key for backward compatibility, but abstracts are no longer truncated.
        self.max_abstract_chars = 0
        self.max_tokens = get_llm_setting(self.config, 'LLM_MAX_TOKENS', 2048, int)
        self.last_error_reason = ''
        self.topic_name = self.config.get('TOPIC_NAME', 'AI')
        self.topic_keywords = self.config.get('TOPIC_KEYWORDS') or []
        self.logger.info(f"PaperAgent 初始化完成，使用 Ollama 模型: {self.model} (host: {self.ollama_host})")

    def _load_config(self, config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as file:
                text = file.read()
            if yaml is not None:
                return yaml.safe_load(text)
            return self._load_simple_yaml(text)
        except Exception as e:
            self.logger.error(f"加载配置文件失败: {e}")
            return {}

    def _load_simple_yaml(self, text):
        config = {}
        current_key = None
        for raw_line in text.splitlines():
            line = raw_line.split('#', 1)[0].rstrip()
            if not line.strip():
                continue
            if line.lstrip().startswith('-') and current_key:
                value = line.lstrip()[1:].strip().strip('"').strip("'")
                config.setdefault(current_key, []).append(value)
                continue
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            if value == '':
                config[key] = []
            elif value.lower() in ('true', 'false'):
                config[key] = value.lower() == 'true'
            else:
                config[key] = value.strip('"').strip("'")
        return config

    def _topic_criteria_text(self):
        keywords = ', '.join(str(k) for k in self.topic_keywords)
        return (
            f"Topic name: {self.topic_name}\n"
            f"TOPIC_KEYWORDS (authoritative HIGH-RECALL scientific scope): {keywords}\n"
            "\n"
            "Semantic verification policy (VERY HIGH RECALL / WIDE REVIEW SCOPE):\n"
            "1. Every paper has already passed deterministic TOPIC_KEYWORDS filtering. "
            "The LLM is NOT a second restrictive topic filter. Its job is only to remove CLEAR semantic false positives.\n"
            "2. TOPIC_KEYWORDS define a BROAD scientific scope. Do NOT narrow the scope to the literal TOPIC_NAME, "
            "and do NOT require the matched concept to be the paper's main focus.\n"
            "3. Classify as Related whenever a configured concept has any scientifically meaningful role in the paper, "
            "including primary, secondary, or exploratory research questions; measured variables; outcomes; phenotypes; symptoms; "
            "clinical characteristics; comorbidities; risk/protective factors; exposures; predictors; biomarkers; mechanisms; pathways; "
            "mediators; moderators; subgroup/stratification variables; treatment effects; adverse effects; behavioral factors; "
            "physiological processes; diagnostic features; prognostic factors; experimental conditions; or meaningful review topics.\n"
            "4. Indirect relationships are still in scope. A paper may be Related even when sleep/circadian biology is connected through "
            "neuropsychiatric disease, metabolism, immunity, inflammation, endocrine signaling, aging, cognition, cardiovascular biology, "
            "drug effects, environmental exposure, behavior, or another intermediate mechanism.\n"
            "5. Reviews, multi-factor studies, and broad disease papers should be retained when sleep/circadian content is one scientifically "
            "meaningful component among several. The concept does NOT have to dominate the abstract.\n"
            "6. A single explicit scientific sentence can be enough for Related if it indicates that the concept is measured, analyzed, "
            "associated with an outcome, mechanistically interpreted, used for subgrouping, or considered as a meaningful clinical/biological factor.\n"
            "7. Classify as Borderline when the matched concept appears in a plausible scientific context but the title/abstract is insufficient "
            "to prove how central or deeply analyzed it is. Borderline MUST be preserved. Examples include broad reviews, secondary endpoints, "
            "brief but meaningful mechanistic references, possible comorbidity links, or title-only records.\n"
            "8. If the paper contains a real scientific sleep/circadian concept but you are unsure whether it is central enough, choose Borderline, "
            "NOT Not Related. Scientific plausibility is enough to preserve the paper for downstream review.\n"
            "9. Classify as Not Related ONLY when there is strong evidence that the keyword match is a clear semantic false positive: "
            "a lexical coincidence, unrelated named entity, ambiguous abbreviation with a different meaning, bibliographic/reference-list artifact, "
            "website/navigation text, metaphorical use, or a molecule/drug/name that is mentioned in a context with no meaningful connection "
            "to the configured scientific topic.\n"
            "10. Mere brevity is NOT a reason to reject. Background/context mentions should be Borderline rather than Not Related whenever they "
            "still describe a scientifically plausible relationship to sleep/circadian biology.\n"
            "11. Missing abstract is NOT negative evidence. Judge from the title and matched keywords; if plausibly in scope, use Borderline.\n"
            "12. PRESERVE RECALL ABOVE PRECISION. If uncertain between Related and Borderline, either is acceptable. "
            "If uncertain between Borderline and Not Related, ALWAYS choose Borderline. "
            "Use Not Related only when you can clearly explain why the match is semantically unrelated."
        )

    def _call_ollama_with_retry(self, messages, temperature=0.2, max_tokens=None):
        """带重试机制的 Ollama 调用"""
        if self.client is None:
            raise RuntimeError("ollama Python package is not installed")
        if max_tokens is None:
            max_tokens = self.max_tokens
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=self._messages_without_thinking(messages),
                    options={
                        'temperature': temperature,
                        'num_predict': max_tokens,
                    },
                    keep_alive=self.keep_alive
                )
                return response['message']['content']
            except Exception as e:
                last_exception = e
                self.logger.warning(f"Ollama 调用失败 (尝试 {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1 and self.retry_base_delay > 0:
                    delay = self.retry_base_delay * (2 ** attempt)
                    self.logger.info(f"Ollama retry backoff {delay:.1f}s before next attempt")
                    time.sleep(delay)
        raise last_exception

    def _messages_without_thinking(self, messages):
        if not self.disable_thinking:
            return messages
        result = []
        inserted = False
        for message in messages or []:
            item = dict(message)
            content = str(item.get("content") or "")
            if not inserted and item.get("role") in ("system", "user"):
                if "/no_think" not in content:
                    content = "/no_think\n" + content
                inserted = True
            item["content"] = content
            result.append(item)
        return result

    def close(self):
        if self.client is not None:
            self._unload_ollama_model()
            self.client = None

    def _unload_ollama_model(self):
        try:
            self.client.generate(model=self.model, prompt="", keep_alive=0)
            self.logger.info(f"Ollama model unloaded: {self.model}")
        except Exception as e:
            self.logger.debug(f"Ollama model unload skipped/failed: {e}")

    def _clip_text_for_llm(self, value, max_chars):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if max_chars and len(text) > max_chars:
            return text[:max_chars].rstrip() + " ..."
        return text

    def _matched_topic_keywords(self, title, abstract):
        """Return literal TOPIC_KEYWORDS matched in title + abstract.

        Uses the same alphanumeric-boundary logic as the deterministic prefilter,
        so the LLM can see why the paper reached semantic verification.
        """
        haystack = f"{title or ''} {abstract or ''}".lower()
        matched = []

        for keyword in self.topic_keywords:
            value = str(keyword or "").strip().lower()
            if not value:
                continue

            pattern = r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(value)
            if re.search(pattern, haystack, flags=re.I):
                matched.append(str(keyword))

        # Preserve config order while removing duplicates.
        seen = set()
        unique = []
        for keyword in matched:
            key = keyword.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(keyword)
        return unique

    def _paper_for_prompt(self, paper):
        raw_title = re.sub(r"\s+", " ", str(paper.get("title", "") or "")).strip()
        raw_abstract = re.sub(r"\s+", " ", str(paper.get("abstract", "") or "")).strip()

        # IMPORTANT:
        # - matched keywords are computed from the COMPLETE title + abstract
        # - abstract is sent to the LLM in full, without character truncation
        # - title clipping is retained only as a defensive compatibility guard
        title = self._clip_text_for_llm(
            raw_title,
            self.max_title_chars,
        )

        return {
            "id": str(paper.get("id", "")),
            "title": title,
            "abstract": raw_abstract,
            "matched_keywords": self._matched_topic_keywords(
                raw_title,
                raw_abstract,
            ),
            "review_input": str(paper.get("review_input", "") or ""),
        }

    def analyze_batch_papers_with_id(self, paper_list):
        """
        同时分析一批论文（将多篇一起打包送入大模型，带 ID）
        参数:
            paper_list (list[dict]): 每项必须有 'id', 'title', 'abstract'
        返回:
            list[dict]: 每篇论文的分析结果，包含原始 id
        """
        self.logger.info(f"Sending {len(paper_list)} papers in batch to Ollama...")

        prompt_parts = []
        for paper in paper_list:
            paper = self._paper_for_prompt(paper)
            prompt_parts.append(f"""
    <item>
    <id>{paper['id']}</id>
    <review_input>{paper['review_input']}</review_input>
    <title>{paper['title']}</title>
    <abstract>{paper['abstract']}</abstract>
    <matched_topic_keywords>{', '.join(paper['matched_keywords'])}</matched_topic_keywords>
    </item>
    """)

        batch_prompt = f"""
    You are performing semantic verification on papers that have ALREADY passed
    a deterministic TOPIC_KEYWORDS keyword prefilter.

    Research topic criteria:
    {self._topic_criteria_text()}

    Important:
    - Judge every paper independently. Do not compare papers within the batch.
    - <matched_topic_keywords> shows which configured keywords literally matched.
      Use these as evidence, not as automatic labels.
    - Related: the matched/configured concept has ANY scientifically meaningful role, including a primary,
      secondary, exploratory, indirect, mechanistic, clinical, behavioral, physiological, prognostic,
      treatment-related, comorbidity, subgroup, biomarker, exposure, predictor, outcome, or review role.
      It does NOT need to be the paper's main topic or dominate the abstract.
    - Borderline: preserve papers where the concept is scientifically plausible/in-scope but the title/abstract
      does not establish how central or deeply analyzed it is. Broad reviews, multi-factor studies,
      secondary endpoints, brief mechanistic links, and title-only records should usually be retained here.
    - Not Related: use ONLY for CLEAR semantic false positives, such as lexical coincidence, unrelated named entity,
      an abbreviation with a different meaning, reference-list/website artifacts, metaphorical use,
      or a matched molecule/name used in a context with no meaningful topic relationship.
    - Do NOT reject merely because the match appears only once or is a secondary/background scientific point.
      If that mention still represents a plausible scientific relationship, use Borderline rather than Not Related.
    - Do NOT require the literal TOPIC_NAME if a configured TOPIC_KEYWORD itself is scientifically meaningful.
    - If <review_input> is title_only or the abstract is empty, missing information is not negative evidence;
      retain plausible records as Borderline.
    - PRESERVE RECALL ABOVE PRECISION. If uncertain between Borderline and Not Related, ALWAYS choose Borderline.
    - Keep each explanation concise (preferably <= 35 words).

    For each <item>, return exactly:
    <result>
    <id>...</id>
    <judgment>Related / Borderline / Not Related</judgment>
    <confidence>0.00-1.00</confidence>
    <matched_concept>short concept or keyword</matched_concept>
    <explanation>concise explanation</explanation>
    </result>

    Return one <result> for every input <item>, in the same order.
    Do not output markdown or any text outside the <result> blocks.

    The papers are as follows:
    {''.join(prompt_parts)}
    """

        try:
            answer = self._call_ollama_with_retry(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a VERY-HIGH-RECALL academic semantic-verification classifier. "
                            "Treat TOPIC_KEYWORDS as a broad authoritative scientific scope. "
                            "Preserve direct, indirect, secondary, exploratory, and clinically meaningful relationships. "
                            "Use Borderline whenever uncertain and reject only unmistakable semantic false positives."
                        )
                    },
                    {"role": "user", "content": batch_prompt}
                ],
                temperature=0,
                max_tokens=self.max_tokens,
            )
            # Parse one result per paper. Keep compatibility with callers that
            # only use id / is_ai_related / judgment / explanation.
            results = []
            pattern = re.compile(
                r"<result>\s*"
                r"<id>(.*?)</id>\s*"
                r"<judgment>(.*?)</judgment>\s*"
                r"<confidence>(.*?)</confidence>\s*"
                r"<matched_concept>(.*?)</matched_concept>\s*"
                r"<explanation>(.*?)</explanation>\s*"
                r"</result>",
                re.DOTALL,
            )

            for match in pattern.finditer(answer):
                paper_id, judgment, confidence_text, matched_concept, explanation = match.groups()

                try:
                    confidence = float(confidence_text.strip())
                except Exception:
                    confidence = 0.0

                confidence = max(0.0, min(1.0, confidence))

                results.append({
                    "id": paper_id.strip(),
                    "is_ai_related": judgment.strip().lower() in ("related", "borderline"),
                    "judgment": judgment.strip(),
                    "confidence": confidence,
                    "matched_concept": matched_concept.strip(),
                    "explanation": explanation.strip(),
                })

            # If the model returns malformed output, let the upstream code treat
            # missing IDs as review failures instead of silently inventing labels.
            if len(results) != len(paper_list):
                self.logger.warning(
                    "Batch parse count mismatch: expected=%s parsed=%s",
                    len(paper_list),
                    len(results),
                )

            return results

        except Exception as e:
            self.last_error_reason = classify_llm_error(e)
            self.logger.error(f"Batch analyze error: {self.last_error_reason}")
            return []

    def batch_analyze_papers_in_batches_concurrent(self, paper_list, batch_size=None, max_workers=1):
        """
        并发批量分析多篇论文
        """
        batch_size = batch_size or self.batch_size
        self.logger.info(f"LLM复核候选 {len(paper_list)} 篇，按 LLM_BATCH_SIZE={batch_size} 分批提交...")

        batches = [
            paper_list[i:i + batch_size]
            for i in range(0, len(paper_list), batch_size)
        ]

        results = []
        if max_workers <= 1:
            for index, batch in enumerate(batches, start=1):
                if index > 1 and self.batch_delay > 0:
                    time.sleep(self.batch_delay)
                results.extend(self.analyze_batch_papers_with_id(batch))
            return results

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {
                executor.submit(self.analyze_batch_papers_with_id, batch): batch
                for batch in batches
            }
            for future in as_completed(future_to_batch):
                try:
                    batch_result = future.result()
                    results.extend(batch_result)
                except Exception as e:
                    self.logger.error(f"[批次分析] 某一批处理失败: {e}")
        return results

    def analyze_paper(self, title, abstract):
        """
        分析单篇论文是否与指定主题相关
        """
        self.logger.info(f"Analyzing paper: {title}")

        prompt = f"""You are an expert in academic literature classification.

    Research Topic:
    {self._topic_criteria_text()}

    Paper Title:
    {title}

    Paper Abstract:
    {abstract}

    This paper should be judged against the configured TOPIC_KEYWORDS scope.
    Determine whether the title/abstract has ANY scientifically meaningful relationship to at least one
    configured keyword concept or a directly/indirectly related mechanism, phenotype, symptom, measurement,
    clinical characteristic, comorbidity, exposure, predictor, outcome, treatment effect, subgroup, biomarker,
    physiological process, behavioral factor, or review topic.
    The concept may be primary, secondary, exploratory, or indirect; it does not need to be the paper's main topic.
    Use Borderline whenever the relationship is scientifically plausible but the available text does not establish
    how central or deeply analyzed it is. A brief but meaningful scientific mention should normally be preserved.
    Do not require the literal TOPIC_NAME. Use Not Related only for CLEAR semantic false positives such as lexical
    coincidence, unrelated named entities, wrong-sense abbreviations, reference/navigation artifacts, metaphorical
    usage, or unrelated molecule/drug usage with no meaningful topic biology. If uncertain, choose Borderline.

    Output ONLY the following XML.

    <result>
    <judgment>Related</judgment>
    <explanation>A concise explanation (within 60 words).</explanation>
    <confidence>0.95</confidence>
    </result>

    Rules:
    - judgment must be exactly one of "Related", "Borderline", or "Not Related"
    - confidence must be between 0 and 1
    - explanation should be concise
    - Do NOT output markdown.
    - Do NOT output any thinking process.
    - Do NOT output anything except the XML.
    """

        try:

            answer = self._call_ollama_with_retry(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a VERY-HIGH-RECALL academic semantic-verification classifier. "
                            "Treat TOPIC_KEYWORDS as a broad authoritative scientific scope. "
                            "Use Borderline for any plausible in-scope uncertainty and reject only unmistakable false positives."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                max_tokens=256
            )

            judgment_match = re.search(
                r"<judgment>\s*(.*?)\s*</judgment>",
                answer,
                re.DOTALL
            )

            explanation_match = re.search(
                r"<explanation>\s*(.*?)\s*</explanation>",
                answer,
                re.DOTALL
            )

            confidence_match = re.search(
                r"<confidence>\s*(.*?)\s*</confidence>",
                answer,
                re.DOTALL
            )

            judgment = (
                judgment_match.group(1).strip()
                if judgment_match
                else "Unable to determine"
            )

            explanation = (
                explanation_match.group(1).strip()
                if explanation_match
                else ""
            )

            try:
                confidence = float(
                    confidence_match.group(1).strip()
                ) if confidence_match else 0.0
            except:
                confidence = 0.0

            return {
                "is_ai_related": judgment.lower() in ("related", "borderline"),
                "judgment": judgment,
                "confidence": confidence,
                "explanation": explanation
            }

        except Exception as e:

            self.last_error_reason = classify_llm_error(e)

            self.logger.error(self.last_error_reason)

            return {
                "is_ai_related": False,
                "judgment": "Error",
                "confidence": 0.0,
                "explanation": self.last_error_reason
            }

    def batch_analyze_papers_concurrent(self, paper_list, max_workers=1):
        """
        并发分析多篇论文（顺序保持）
        """
        results = [None] * len(paper_list)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self.analyze_paper, paper['title'], paper['abstract']): idx
                for idx, paper in enumerate(paper_list)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    self.logger.error(f"[并发分析] 处理第 {idx} 篇论文时失败: {e}")
                    results[idx] = {
                        'is_ai_related': False,
                        'judgment': "Error",
                        'explanation': f"Error: {e}",
                        'thinking': "Analysis failed due to exception"
                    }
        return results

    def batch_analyze_papers(self, papers):
        """顺序批量分析（保留方法）"""
        results = []
        for i, paper in enumerate(papers):
            self.logger.info(f"分析第 {i+1}/{len(papers)} 篇论文")
            result = self.analyze_paper(paper['title'], paper['abstract'])
            results.append({
                'paper': paper,
                'analysis': result
            })
        return results

    def save_analysis_results(self, results, output_file='analysis_results.json'):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            self.logger.info(f"分析结果已保存至 {output_file}")
            return True
        except Exception as e:
            self.logger.error(f"保存分析结果时出错: {e}")
            return False


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    agent = PaperAgent()
    test_paper = {
        'title': 'The evolutionary significance of post-transcriptional gene regulation',
        'abstract': 'Understanding the molecular mechanisms that give rise to phenotypic diversity ...'
    }
    result = agent.analyze_paper(test_paper['title'], test_paper['abstract'])
    print(f"是否有关: {result['is_ai_related']}")
    print(f"判断: {result['judgment']}")
    print(f"解释: {result['explanation']}")
