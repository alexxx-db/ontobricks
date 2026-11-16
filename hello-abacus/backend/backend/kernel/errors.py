class Unauthorized(Exception):
    """No signed-in user. runtime/ maps this to HTTP 401."""
