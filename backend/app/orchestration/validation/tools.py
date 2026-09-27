"""The message check's tool-call schema — what the LLM fills in.

Split from `validate.py` to match the slice layout: `tools.py` is what the
LLM fills in, `validate.py` is what runs.
"""

from pydantic import BaseModel, Field


# Mirrors the `content_check` JSON schema the prompt was written against
# (2026-09-26); the tool's name stays the class name. Field order is the order
# the model writes in, so `reasoning` comes before the flags it justifies.
class UserMsgValidation(BaseModel):
    """Check the user's message for harmful, security and incoherence
    before anything else in the app reads it.
    """

    reasoning: str = Field(
        ...,
        description="Concise justification describing how the content was evaluated for security and harmfulness, and how the language was identified.",
    )
    security_issue: bool = Field(
        ...,
        description="Indicates if there is a security issue (e.g. phishing, malware, credential harvesting) present in the content.",
    )
    harmful_content: bool = Field(
        ...,
        description="Indicates if the content contains harmful elements (e.g. hate speech, threats, self-harm, bullying, encouragement of violence or dangerous acts).",
    )
    gibberish_or_incoherent: bool = Field(
        ...,
        description="Indicates if the content is mostly gibberish, incoherent, random characters, or non-linguistic noise.",
    )
