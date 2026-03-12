DEFAULT_LLM_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4.1-mini",
    "claude": "claude-3-5-haiku-latest",
}


def build_translation_prompt(target_language: str, numbered_lines: str) -> str:
    return (
        f"Translate the following numbered subtitle lines to {target_language}. "
        f"For technical terms and proper nouns, translate only if a widely accepted translation exists; otherwise keep the original. "
        f"Return ONLY the translations in the exact same numbered format: number|translated text. "
        f"Keep the numbering identical. Do not add explanations.\n\n"
        f"{numbered_lines}"
    )


def parse_numbered_translations(text: str) -> dict[int, str]:
    translations: dict[int, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if "|" not in line:
            continue
        index_text, translated_text = line.split("|", 1)
        try:
            index = int(index_text.strip())
        except ValueError:
            continue
        translated_text = translated_text.strip()
        if translated_text:
            translations[index] = translated_text
    return translations


class LLMTranslatorProvider:
    def __init__(self, provider: str, api_key: str, model: str | None = None):
        self.provider = provider
        self.api_key = api_key.strip()
        self.model = model or DEFAULT_LLM_MODELS[provider]

    def translate_batch(self, target_language: str, batch) -> dict[int, str]:
        if not self.api_key:
            raise RuntimeError(
                f"No API key set for {self.provider}. Enter and apply your key in Settings first."
            )

        numbered_lines = "\n".join(f"{entry.index}|{entry.original_text}" for entry in batch)
        prompt = build_translation_prompt(target_language, numbered_lines)

        if self.provider == "gemini":
            text = self._translate_with_gemini(prompt)
        elif self.provider == "openai":
            text = self._translate_with_openai(prompt)
        elif self.provider == "claude":
            text = self._translate_with_claude(prompt)
        else:
            raise RuntimeError(f"Unsupported translation provider: {self.provider}")

        return parse_numbered_translations(text)

    def _translate_with_gemini(self, prompt: str) -> str:
        from google import genai

        client = genai.Client(api_key=self.api_key)
        response = client.models.generate_content(model=self.model, contents=prompt)
        response_text = (response.text or "").strip()
        if not response_text:
            raise RuntimeError(f"{self.model}: empty response")
        return response_text

    def _translate_with_openai(self, prompt: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "You are a subtitle translator. Return only numbered translations in the requested format.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        response_text = (response.choices[0].message.content or "").strip()
        if not response_text:
            raise RuntimeError(f"{self.model}: empty response")
        return response_text

    def _translate_with_claude(self, prompt: str) -> str:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0,
            system="You are a subtitle translator. Return only numbered translations in the requested format.",
            messages=[{"role": "user", "content": prompt}],
        )
        parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        response_text = "".join(parts).strip()
        if not response_text:
            raise RuntimeError(f"{self.model}: empty response")
        return response_text