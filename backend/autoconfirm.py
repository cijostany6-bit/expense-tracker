"""
Cognito Pre-SignUp trigger.

For a portfolio/demo app we auto-confirm new users and auto-verify their email
so sign-up is instant (no verification email needed).

NOTE: in a real product you would NOT do this — you would keep email
verification so people can only register addresses they actually own.
"""


def handler(event, context):
    event["response"]["autoConfirmUser"] = True
    event["response"]["autoVerifyEmail"] = True
    return event
