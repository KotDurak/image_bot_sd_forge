module.exports = {
  apps : [{
    name: "my_bot",
    script: "./main.py",
    // Используйте двойные обратные слеши в путях для Windows
    interpreter: "D:\\image_bot\\.venv\\Scripts\\python.exe",
    watch: false,
    env: {
      NODE_ENV: "development",
    }
  }]
}