from typing import Any

from luckydonaldUtils.logger import ColoredFormatter, ColoredStreamHandler, logging

from .fully_qualified_name import fqn

# ColoredFormatter.Color.mapping['INFO'] = 'grey'
ColoredFormatter.Color.mapping['TRACE'] = 'grey'

class ColoredFormatterKwargs(ColoredFormatter):
    def __init__(self, *args, date_formatter=None, **kwargs):
        super().__init__(date_formatter=date_formatter)
    # end def
# end class


def get_uvicorn_log_config(*, disable_existing_loggers: bool = False, project: str | None = None) -> dict[str, Any]:
    config = {
        "version": 1,
        "disable_existing_loggers": disable_existing_loggers,
        "formatters": {
            "default": {
                "()": fqn(ColoredFormatterKwargs),
                "format": "%(levelprefix)s %(message)s",
                "use_colors": True,
            },
            "access": {
                "()": fqn(ColoredFormatterKwargs),
                "format": "%(levelprefix)s %(client_addr)s - '%(request_line)s' %(status_code)s",
                "use_colors": True,
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": fqn(ColoredStreamHandler),
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": fqn(ColoredStreamHandler),
                "stream": "ext://sys.stdout",
            },
            "root": {
                "formatter": "default",
                "class": fqn(ColoredStreamHandler),
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "uvicorn": {
                "level": "INFO",
                "handlers": ["default"],
            },
            "uvicorn.error": {
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["access"],
                "propagate": False,
            },
            "uvicorn.asgi.trace": {
                "level": "INFO", # yes, they only log at "TRACE" level.
                "handlers": ["default"],
                "propagate": False,
            },
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["root"],
            "propagate": False,
        },
    }
    if project:
        config['loggers'][project] = {
            "level": "DEBUG",
            "handlers": ["default"],
            "propagate": False,
        }
    # end if
    return config
# end def
