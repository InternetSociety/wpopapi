class DomainError(Exception):
    status_code = 400


class InvalidCredentialsError(DomainError):
    status_code = 401


class InactiveUserError(DomainError):
    status_code = 403


class EmailAlreadyExistsError(DomainError):
    status_code = 409


class UserNotFoundError(DomainError):
    status_code = 404


class ProhibitedUserOperationError(DomainError):
    status_code = 400


class InvalidUserDataError(DomainError):
    status_code = 400
