import logging
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.credentials import RefreshableCredentials
from botocore.exceptions import ClientError
from botocore.session import get_session

logger = logging.getLogger(__name__)


class RefreshableSession:
    def __init__(
        self,
        role_arn: str,
        session_name: str,
        session_duration: int = 3600,
        region_name: Optional[str] = None,
        sts_client=None,
        **session_kwargs,
    ):
        if not role_arn:
            raise ValueError("role_arn is required")
        if not session_name:
            raise ValueError("session_name is required")

        self.role_arn = role_arn
        self.session_name = session_name
        self.session_duration = session_duration
        self.region_name = region_name
        self.session_kwargs = session_kwargs
        self.sts_client = sts_client or boto3.client(
            "sts", region_name=region_name, config=BotoConfig(retries={"mode": "standard"})
        )

        logger.info(f"Initialized RefreshableSession for role: {role_arn}")

    def __get_session_credentials(self):
        try:
            logger.debug(f"Assuming role: {self.role_arn}")
            resp = self.sts_client.assume_role(
                RoleArn=self.role_arn,
                RoleSessionName=self.session_name,
                DurationSeconds=self.session_duration,
            ).get("Credentials")

            logger.debug("Successfully assumed role")
            return {
                "access_key": resp.get("AccessKeyId"),
                "secret_key": resp.get("SecretAccessKey"),
                "token": resp.get("SessionToken"),
                "expiry_time": resp.get("Expiration").isoformat(),
            }
        except ClientError as e:
            logger.error(f"Failed to assume role {self.role_arn}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error assuming role {self.role_arn}: {e}")
            raise

    def refreshable_session(self) -> boto3.Session:
        try:
            refreshable_credentials = RefreshableCredentials.create_from_metadata(
                metadata=self.__get_session_credentials(),
                refresh_using=self.__get_session_credentials,
                method="sts-assume-role",
            )

            session = get_session()
            session._credentials = refreshable_credentials

            # Ensure region is set
            session_kwargs = self.session_kwargs.copy()
            if self.region_name and "region_name" not in session_kwargs:
                session_kwargs["region_name"] = self.region_name

            return boto3.Session(botocore_session=session, **session_kwargs)
        except Exception as e:
            logger.error(f"Failed to create refreshable session: {e}")
            raise
