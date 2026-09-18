"""Dependency-free prompt model with a string view for existing callers."""


class PromptText(str):
    def __new__(cls, system, user, *, glossary="", relevance=""):
        value = super().__new__(cls, f"{system}\n\n{user}" if system else user)
        value.system = system
        value.user = user
        value.glossary = glossary
        value.relevance = relevance
        return value

    def with_user(self, user, *, glossary=None):
        return PromptText(self.system, user, glossary=self.glossary if glossary is None else glossary,
                          relevance=self.relevance)
