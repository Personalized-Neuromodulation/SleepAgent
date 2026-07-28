from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class _Rule:
    allow: bool
    pattern: str

    def matches(self, target: str) -> bool:
        # Modern publisher robots files use Google's * and $ extensions.  The
        # stdlib RobotFileParser does not implement them correctly (for example
        # Springer's "Allow: /journal*"), which caused permitted journal pages
        # to be reported as blocked.
        expression = re.escape(self.pattern)
        expression = expression.replace(r"\*", ".*")
        if expression.endswith(r"\$"):
            expression = expression[:-2] + "$"
        return re.match(expression, target) is not None

    @property
    def specificity(self) -> int:
        return len(self.pattern.replace("*", "").rstrip("$"))


class _RobotsPolicy:
    def __init__(self, text: str):
        self.groups: list[tuple[list[str], list[_Rule]]] = []
        agents: list[str] = []
        rules: list[_Rule] = []
        saw_rule = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.casefold()
            if field == "user-agent":
                if saw_rule:
                    self.groups.append((agents, rules))
                    agents, rules, saw_rule = [], [], False
                agents.append(value.casefold())
            elif field in {"allow", "disallow"} and agents:
                saw_rule = True
                if value:
                    rules.append(_Rule(field == "allow", value))
        if agents:
            self.groups.append((agents, rules))

    def can_fetch(self, user_agent: str, url: str) -> bool:
        product = user_agent.casefold().split("/", 1)[0].split(None, 1)[0]
        specific: list[_Rule] = []
        wildcard: list[_Rule] = []
        best_agent_length = -1
        for agents, rules in self.groups:
            matches = [agent for agent in agents if agent != "*" and agent in product]
            if matches:
                length = max(map(len, matches))
                if length > best_agent_length:
                    specific = list(rules)
                    best_agent_length = length
                elif length == best_agent_length:
                    specific.extend(rules)
            elif "*" in agents:
                wildcard.extend(rules)
        applicable = specific if best_agent_length >= 0 else wildcard
        target = urlsplit(url).path or "/"
        if urlsplit(url).query:
            target += "?" + urlsplit(url).query
        matched = [rule for rule in applicable if rule.matches(target)]
        if not matched:
            return True
        longest = max(rule.specificity for rule in matched)
        # Allow wins when rules have equal specificity.
        return any(rule.allow for rule in matched if rule.specificity == longest)


class RobotsCache:
    def __init__(self, http_client, user_agent="SleepAgent"):
        self.http = http_client
        self.user_agent = user_agent
        self._cache = {}
        self._locks = {}
        self._guard = threading.Lock()

    def check(self, url):
        parts = urlsplit(url)
        domain = f"{parts.scheme}://{parts.netloc}"
        with self._guard:
            lock = self._locks.setdefault(domain, threading.Lock())
        with lock:
            if domain not in self._cache:
                robots_url = f"{domain}/robots.txt"
                try:
                    status, body, _, _ = self.http.get(robots_url)
                    if status >= 400:
                        self._cache[domain] = ("robots_unavailable", None)
                    else:
                        self._cache[domain] = (
                            "allowed",
                            _RobotsPolicy(body.decode("utf-8", errors="replace")),
                        )
                except Exception:
                    self._cache[domain] = ("robots_unavailable", None)
        status, parser = self._cache[domain]
        if parser is None:
            return status, False
        allowed = parser.can_fetch(self.user_agent, url)
        return ("allowed" if allowed else "disallowed"), allowed
