import logging
import os
import time

import jwt


LOGGER = logging.getLogger()

AUTHORIZED_RESPONSE = {
    "policyDocument": {
        "Version": "2012-10-17",
         "Statement": [
             {
                 "Action": "execute-api:Invoke",
                 "Resource": [f"arn:aws:execute-api:{os.environ['API_REGION']}:{os.environ['ACCOUNT_ID']}:{os.environ['API_ID']}*"],
                 "Effect": "Allow"
        }]
    }
}

UNAUTHORIZED_RESPONSE = {
    "policyDocument": {
        "Version": "2012-10-17",
         "Statement": [
             {
                 "Action": "*",
                 "Resource": ["*"],
                 "Effect": "Deny"
        }]
    }
}

BASE_ISSUER_URL = f"https://cognito-idp.{os.environ['API_REGION']}.amazonaws.com/{os.environ['COGNITO_USER_POOL_ID']}"
JWKS_URL = f"{BASE_ISSUER_URL}/.well-known/jwks.json"

VALID_TOKEN_USE = ["id"]


def _silence_noisy_loggers():
    """Silence chatty libraries for better logging"""
    for logger in ['boto3', 'botocore',
                   'botocore.vendored.requests.packages.urllib3']:
        logging.getLogger(logger).setLevel(logging.WARNING)


def _configure_logger():
    """Configure python logger for lambda function"""
    default_log_args = {
        "level": logging.DEBUG if os.environ.get("VERBOSE", False) else logging.INFO,
        "format": "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        "datefmt": "%d-%b-%y %H:%M",
        "force": True,
    }
    logging.basicConfig(**default_log_args)


def _valid_token(token, audience):
    """Check JWT token parameters' validity

    :param token: Dictionary
    :param audience: String

    :rtype: Boolean
    """
    expiry_time = token.get("exp")
    if not expiry_time:
        LOGGER.error("Token does not contain 'exp' key")
        return False
    
    if int(time.time()) > expiry_time:
        LOGGER.error("Token has expired")
        return False

    aud = token.get("aud")
    if not aud:
        LOGGER.error("Missing 'aud' key in token")
        return False
    
    if aud != audience:
        LOGGER.error(f"Audience client {aud} does not match")
        return False
    
    iss = token.get("iss")
    if not iss:
        LOGGER.error("Missing 'iss' key in token")
        return False
    
    if iss != BASE_ISSUER_URL:
        LOGGER.error(f"Issuer URL {iss} did not match")
        return False

    token_use = token.get("token_use")
    if not token_use:
        LOGGER.error("token_use missing from token")
        return False
    
    if token_use not in VALID_TOKEN_USE:
        LOGGER.error(f"token_use {token_use} is not a valid option")
        return False
    
    LOGGER.info("Decoded token is verified to be valid")
    return True


def lambda_handler(event, context):
    """What executes when the program is run"""

    # configure python logger for Lambda
    _configure_logger()
    # silence chatty libraries for better logging
    _silence_noisy_loggers()

    auth_token = event.get("authorizationToken")
    if not auth_token:
        LOGGER.error("No authorizationToken passed in")
        return UNAUTHORIZED_RESPONSE

    token_string = auth_token.replace("Bearer ", "")
    if not token_string:
        LOGGER.error("empty token provided")
        return UNAUTHORIZED_RESPONSE
    
    LOGGER.info("Attempting to extract headers from the token string")
    try:
        token_header = jwt.get_unverified_header(token_string)
    except jwt.exceptions.DecodeError as err:
        LOGGER.error(
            f"Unable to extracat headers from the token string: {err}")
        return UNAUTHORIZED_RESPONSE

    LOGGER.info(f"Initializing jwks client for: {JWKS_URL}")
    jwks_client = jwt.PyJWKClient(JWKS_URL)

    LOGGER.info("Trying to get the signing key from the token header")
    try:
        key = jwks_client.get_signing_key(token_header["kid"]).key
    except jwt.exceptions.PyJWKSetError as err:
        LOGGER.error(f"Unable to fetch keys: {err}")
        return UNAUTHORIZED_RESPONSE
    except jwt.exceptions.PyJWKClientError as err:
        LOGGER.error(f"No matching key found: {err}")
        return UNAUTHORIZED_RESPONSE
    
    algorithm = token_header.get("alg")
    if not algorithm:
        LOGGER.error("Token header did not contain the alg key")
        return UNAUTHORIZED_RESPONSE
    
    audience_client = os.environ["COGNITO_APP_CLIENT_ID"]
    LOGGER.info(f"Trying to decode the token string for client: {audience_client}")
    try:
        decoded_token = jwt.decode(
            token_string, 
            key, 
            [algorithm], 
            audience=audience_client
        )
    except jwt.exceptions.DecodeError as err:
        LOGGER.error(f"Unable to decode token string: {err}")
        return UNAUTHORIZED_RESPONSE
    except jwt.exceptions.MissingRequiredClaimError as err:
        LOGGER.error(f"Unable to decode token: {err}")
        return UNAUTHORIZED_RESPONSE
    except jwt.exceptions.ExpiredSignatureError as err:
        LOGGER.error(f"Signature has expired: {err}")
        return UNAUTHORIZED_RESPONSE
    
    if not _valid_token(decoded_token, audience_client):
        return UNAUTHORIZED_RESPONSE
    
    return AUTHORIZED_RESPONSE       
