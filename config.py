import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Config:
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "CloudRSVPSecret123")

    # AWS
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # Cognito
    COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID")
    COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
    COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")

    # Session Configuration
    SESSION_PERMANENT = False

    # Upload Configuration (for future S3 integration)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # Future DynamoDB Table Names
    EVENTS_TABLE = "CloudRSVPEvents"
    USERS_TABLE = "CloudRSVPUsers"

    @staticmethod
    def validate():
        """
        Validate required environment variables.
        """
        required = [
            "AWS_REGION",
            "COGNITO_USER_POOL_ID",
            "COGNITO_CLIENT_ID",
            "COGNITO_CLIENT_SECRET",
            "SECRET_KEY",
        ]

        missing = [key for key in required if not os.getenv(key)]

        if missing:
            raise RuntimeError(
                "Missing environment variables: " + ", ".join(missing)
            )
