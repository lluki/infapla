{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.infapla;
in {
  options.services.infapla = {
    enable = mkEnableOption "InFaPla - Intelligent Family Planner";

    package = mkOption {
      type = types.package;
      default = pkgs.callPackage ../default.nix { };
      description = "The infapla package to use.";
    };

    port = mkOption {
      type = types.port;
      default = 8766;
      description = "Port to listen on.";
    };

    host = mkOption {
      type = types.str;
      default = "127.0.0.1";
      description = "Host to listen on.";
    };

    dataDir = mkOption {
      type = types.str;
      default = "/var/lib/infapla/data";
      description = "Directory for storage and git repository.";
    };

    user = mkOption {
      type = types.str;
      default = "lukas";
      description = "User to run the service as.";
    };

    group = mkOption {
      type = types.str;
      default = "users";
      description = "Group to run the service as.";
    };

    agyBin = mkOption {
      type = types.str;
      default = "/home/lukas/.local/bin/agy";
      description = "Path to agy binary.";
    };

    agyModel = mkOption {
      type = types.str;
      default = "gemini-3.8-flash-low";
      description = "Model for agy.";
    };

    agyEffort = mkOption {
      type = types.str;
      default = "low";
      description = "Reasoning effort for agy.";
    };

    telegramBotToken = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = "Optional Telegram bot token.";
    };

    gitCommitInterval = mkOption {
      type = types.int;
      default = 30;
      description = "Interval in seconds between periodic git auto-commits.";
    };
  };

  config = mkIf cfg.enable {
    systemd.services.infapla = {
      description = "InFaPla - Intelligent Family Planner";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Restart = "always";
        User = cfg.user;
        Group = cfg.group;
        StateDirectory = "infapla";
      };

      environment = {
        INFAPLA_DATA_DIR = cfg.dataDir;
        INFAPLA_HOST = cfg.host;
        INFAPLA_PORT = toString cfg.port;
        INFAPLA_GIT_INTERVAL = toString cfg.gitCommitInterval;
        AGY_BIN = cfg.agyBin;
        AGY_MODEL = cfg.agyModel;
        AGY_EFFORT = cfg.agyEffort;
        HOME = "/home/${cfg.user}";
      } // optionalAttrs (cfg.telegramBotToken != null) {
        TELEGRAM_BOT_TOKEN = cfg.telegramBotToken;
      };

      script = ''
        exec ${cfg.package}/bin/infapla
      '';
    };
  };
}
