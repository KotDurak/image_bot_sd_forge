module.exports = {
  apps : [{
    name: "my_bot",
    script: "./main.py",
    // Используйте двойные обратные слеши в путях для Windows
    interpreter: "C:\\bot_for_sd\\.venv\\Scripts\\python.exe",
    cwd: "C:\\bot_for_sd",
    watch: false,
    restart_delay: 3000,
    max_restarts: 10,
    min_uptime: "30s",
    watch: false,
    env: {
      NODE_ENV: "development",
    },
    error_file: "logs/err.log",
    out_file: "/dev/null",
    log_date_format: "YYYY-MM-DD HH:mm:ss",
    log_rotator: {
      max_size: "10M",
      max_files: 3
    },
  }]
}