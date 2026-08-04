from abc import ABC, abstractmethod
from dataclasses import dataclass
from app.testing.faults import inject


class AIProviderError(Exception):
    pass


class AIProviderTimeout(AIProviderError):
    pass


class AIProviderRateLimited(AIProviderError):
    pass


class AIProviderUnavailable(AIProviderError):
    pass


@dataclass(frozen=True)
class AIResult:
    content: bytes
    input_tokens: int
    output_tokens: int
    duration_ms: int
    score: int | None = None


class AIProvider(ABC):
    @abstractmethod
    def generate(self, content: bytes, instructions: list[str]) -> AIResult: ...
    @abstractmethod
    def review(self, content: bytes) -> AIResult: ...
    @abstractmethod
    def revise(self, content: bytes, comments: list[str]) -> AIResult: ...
    @abstractmethod
    def test_connection(self) -> bool: ...


class MockAIProvider(AIProvider):
    def __init__(self, review_scores: list[int] | None = None):
        self.review_scores = list(review_scores or [100])
        self.calls = 0

    def generate(self, content: bytes, instructions: list[str]) -> AIResult:
        inject("AI_PROVIDER_TIMEOUT")
        self.calls += 1
        return AIResult(content + b"\nmock-generated", len(content) // 4, 4, 1000)

    def review(self, content: bytes) -> AIResult:
        inject("AI_PROVIDER_TIMEOUT")
        self.calls += 1
        score = self.review_scores.pop(0) if self.review_scores else 100
        return AIResult(b"", len(content) // 4, 1, 1000, score)

    def revise(self, content: bytes, comments: list[str]) -> AIResult:
        inject("AI_PROVIDER_TIMEOUT")
        self.calls += 1
        suffix = ("\nmock-revision:" + "|".join(comments)).encode()
        return AIResult(content + suffix, len(content) // 4, len(suffix) // 4 + 1, 1000)

    def test_connection(self) -> bool:
        return True


class DisabledExternalProvider(AIProvider):
    def _disabled(self):
        raise AIProviderUnavailable("External AI communication is disabled")

    def generate(self, content: bytes, instructions: list[str]) -> AIResult:
        return self._disabled()

    def review(self, content: bytes) -> AIResult:
        return self._disabled()

    def revise(self, content: bytes, comments: list[str]) -> AIResult:
        return self._disabled()

    def test_connection(self) -> bool:
        return False


class OpenAIProviderStub(DisabledExternalProvider):
    pass


class AnthropicProviderStub(DisabledExternalProvider):
    pass
