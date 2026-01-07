"""Authentication and authorization middleware."""

import inspect
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.i18n import t
from src.storage.database import Database
from src.storage.models import User, UserRole
from src.utils.config import Config

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseMiddleware):
    """
    Middleware for user authentication and authorization.

    - Creates user record on first interaction
    - Automatically grants owner role to configured admin IDs
    - Works in both private chats and groups
    - Injects user object into handler data
    """

    def __init__(self, config: Config, database: Database):
        self.config = config
        self.database = database
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:

        # Extract user from event
        user_id: int | None = None
        username: str | None = None
        lang: str = self.config.language
        chat_type: str = "private"

        if isinstance(event, Message):
            if event.from_user:
                user_id = event.from_user.id
                username = event.from_user.username
                lang = event.from_user.language_code or lang
            if event.chat:
                chat_type = event.chat.type
        elif isinstance(event, CallbackQuery):
            if event.from_user:
                user_id = event.from_user.id
                username = event.from_user.username
                lang = event.from_user.language_code or lang
            if event.message and event.message.chat:
                chat_type = event.message.chat.type
        else:
            logger.warning(f"AuthMiddleware: Unknown event type: {type(event)}")

        if user_id is None:
            logger.warning(f"AuthMiddleware: user_id is None for event type {type(event)}")
            return await handler(event, data)

        # Get or create user
        user = await self.database.get_or_create_user(user_id, username)

        # Check if user should be owner (from config)
        if user_id in self.config.telegram.admin_ids and user.role != UserRole.OWNER:
            user.role = UserRole.OWNER
            await self.database.update_user(user)
            logger.info("Granted OWNER role to user %s (from config)", user_id)

        # Update username if changed
        if username and user.username != username:
            user.username = username
            await self.database.update_user(user)

        # Normalize language
        if lang and lang.startswith("ru"):
            user_lang = "ru"
        else:
            user_lang = user.language if user.language in ("ru", "en") else "en"

        # Inject into handler data
        data["user"] = user
        data["user_lang"] = user_lang
        data["chat_type"] = chat_type
        data["is_group"] = chat_type in ("group", "supergroup")

        # Legacy compatibility (will be removed later)
        data["is_admin"] = user.is_admin()
        data["is_moderator"] = user.is_operator()

        return await handler(event, data)


def require_role(min_role: UserRole):
    """
    Decorator to require minimum role for a handler.

    Role hierarchy:
    - OWNER (100): Create servers, assign roles
    - ADMIN (75): All server commands
    - OPERATOR (50): Start/stop/restart
    - PLAYER (10): View only

    Usage:
        @router.message(Command("start_server"))
        @require_role(UserRole.OPERATOR)
        async def start_server(message: Message, user: User, ...):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            user: User | None = kwargs.get("user")

            if not user:
                return

            # Check role hierarchy using level comparison
            if user.role.level < min_role.level:
                # No permission
                event = args[0] if args else None
                lang = kwargs.get("user_lang", "ru")

                role_names = {
                    UserRole.OWNER: t("roles.owner", lang),
                    UserRole.ADMIN: t("roles.admin", lang),
                    UserRole.OPERATOR: t("roles.operator", lang),
                    UserRole.PLAYER: t("roles.player", lang),
                }
                required_role = role_names.get(min_role, str(min_role))

                if isinstance(event, Message):
                    await event.answer(
                        t("roles.no_permission_detailed", lang, required=required_role)
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        t("roles.no_permission", lang),
                        show_alert=True,
                    )
                return

            # Filter kwargs to only pass what the function accepts
            sig = inspect.signature(func)
            valid_params = set(sig.parameters.keys())
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

            return await func(*args, **filtered_kwargs)

        return wrapper

    return decorator


def owner_only(func: Callable) -> Callable:
    """Shortcut decorator for owner-only commands."""
    return require_role(UserRole.OWNER)(func)


def admin_only(func: Callable) -> Callable:
    """Shortcut decorator for admin-only commands."""
    return require_role(UserRole.ADMIN)(func)


def operator_only(func: Callable) -> Callable:
    """Shortcut decorator for operator-only commands."""
    return require_role(UserRole.OPERATOR)(func)


async def check_role(
    user: User | None,
    min_role: UserRole,
    callback: "CallbackQuery",
    lang: str = "ru",
) -> bool:
    """
    Check if user has required role for callback handlers.

    Use this in callback handlers instead of @require_role decorator.

    Returns:
        True if user has permission, False otherwise (and sends alert)
    """
    if not user:
        await callback.answer(t("roles.no_permission", lang), show_alert=True)
        return False

    if user.role.level < min_role.level:
        await callback.answer(t("roles.no_permission", lang), show_alert=True)
        return False

    return True
