import pyomo.common.config
import logging.config
import toml
import os
import importlib

_log = logging.getLogger(__name__)
default_binary_url = "https://github.com/IDAES/idaes-ext/releases/download/1.0.1/"

default_config = """
use_idaes_solvers = true
logger_capture_solver = true
logger_tags = [
    "framework",
    "model",
    "flowsheet",
    "unit",
    "control_volume",
    "properties",
    "reactions",
]
valid_logger_tags = [
    "framework",
    "model",
    "flowsheet",
    "unit",
    "control_volume",
    "properties",
    "reactions",
]
[logging]
  version = 1
  disable_existing_loggers = false
  [logging.formatters.default_format]
    format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
  [logging.handlers.console]
    class = "logging.StreamHandler"
    formatter = "default_format"
    stream = "ext://sys.stdout"
  [logging.loggers.idaes]
    level = "INFO"
    propagate = true
    handlers = ["console"]
  [logging.loggers."idaes.solve"]
    level = "INFO"
    propagate = false
    handlers = ["console"]
  [logging.loggers."idaes.init"]
    level = "INFO"
    propagate = false
    handlers = ["console"]
  [logging.loggers."idaes.model"]
    level = "INFO"
    propagate = false
    handlers = ["console"]
"""

def new_idaes_config_block():
    _config = pyomo.common.config.ConfigBlock("idaes", implicit=False)
    _config.declare(
        "logging",
        pyomo.common.config.ConfigBlock(
            implicit=True,
            description="Logging configuration dictionary",
            doc="This stores the logging configuration. See the Python "
            "logging.config.dictConfig() documentation for details.",
        ),
    )

    _config.declare(
        "use_idaes_solvers",
        pyomo.common.config.ConfigValue(
            default=True,
            domain=bool,
            description="Add the IDAES bin directory to the path.",
            doc="Add the IDAES bin directory to the path such that solvers provided "
            "by IDAES will be used in preference to previously installed solvers.",
        ),
    )

    _config.declare(
        "valid_logger_tags",
        pyomo.common.config.ConfigValue(
            default=set(),
            domain=set,
            description="List of valid logger tags",
        ),
    )

    _config.declare(
        "logger_tags",
        pyomo.common.config.ConfigValue(
            default=set(),
            domain=set,
            description="List of logger tags to allow",
        ),
    )

    _config.declare(
        "logger_capture_solver",
        pyomo.common.config.ConfigValue(
            default=True,
            description="Solver output captured by logger?",
        ),
    )

    d = toml.loads(default_config)
    _config.set_value(d)
    logging.config.dictConfig(_config["logging"])
    return _config


def read_config(read_config, write_config):
    """Read either a TOML formatted config file or a configuration dictionary.
    Args:
        config: A config file path or dict
    Returns:
        None
    """
    config_file = None
    if read_config is None:
        return
    elif isinstance(read_config, dict):
        pass  # don't worry this catches ConfigBlock too it seems
    else:
        config_file = read_config
        try:
            with open(config_file, "r") as f:
                write_config = toml.load(f)
        except IOError:  # don't require config file
            _log.debug("Config file {} not found (this is okay)".format(read_config))
            return
    write_config.set_value(read_config)
    logging.config.dictConfig(write_config["logging"])
    if config_file is not None:
        _log.debug("Read config {}".format(config_file))


def create_dir(d):
    """Create a directory if it doesn't exist.

    Args:
        d(str): directory path to create

    Retruns:
        None
    """
    if os.path.exists(d):
        return
    else:
        os.mkdir(d)


def get_data_directory():
    """Return the standard data directory for idaes, based on the OS."""
    try:
        if os.name == 'nt':  # Windows
            data_directory = os.path.join(os.environ['LOCALAPPDATA'], "idaes")
        else:  # any other OS
            data_directory = os.path.join(os.environ['HOME'], ".idaes")
    except AttributeError:
        data_directory = None
    # Standard location for executable binaries.
    if data_directory is not None:
        bin_directory = os.path.join(data_directory, "bin")
    else:
        bin_directory = None

    # Standard location for IDAES library files.
    if data_directory is not None:
        lib_directory = os.path.join(data_directory, "lib")
    else:
        lib_directory = None

    return data_directory, bin_directory, lib_directory


def setup_environment(bin_directory, lib_directory, use_idaes_solvers):
    if use_idaes_solvers:
        # Add IDAES stuff to the path unless you configure otherwise
        os.environ['PATH'] = os.pathsep.join([bin_directory, os.environ['PATH']])
        if os.name == 'nt':  # Windows (this is to find MinGW libs)
            os.environ['PATH'] = os.pathsep.join([os.environ['PATH'], lib_directory])
        else:
            os.environ['LD_LIBRARY_PATH'] = os.pathsep.join(
                [os.environ.get('LD_LIBRARY_PATH', ''), lib_directory]
            )
