"""`UserMsgValidation`, the tool the message check's model fills in."""

from pydantic import BaseModel, Field


# NOTE: field order is the order the model writes in, so `reasoning` comes
# before the flags it justifies. The docstring and descriptions are prompt text.
class UserMsgValidation(BaseModel):
    """Check the user's message for security threats, harmful content and
    gibberish before anything else in the app reads it.
    """

    reasoning: str = Field(
        ...,
        description="Concise justification describing how the content was evaluated for security, harmfulness and gibberish.",
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
