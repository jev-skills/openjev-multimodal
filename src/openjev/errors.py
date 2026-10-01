class APIError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status
