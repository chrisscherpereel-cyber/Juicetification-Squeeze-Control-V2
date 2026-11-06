class ApiError(Exception): pass
class RateLimitError(Exception):
    backoff = None
