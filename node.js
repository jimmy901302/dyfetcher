const express = require('express');
const app = express();

// 读取 Railway 环境变量 PORT，本地开发默认 3000
const port = process.env.PORT || 3000;

// 【代码更改1】修改响应内容
app.get('/', (req, res) => {
  res.send('Hello Railway! （代码已修改）');
});

// 【代码更改2】新增路由
app.get('/about', (req, res) => {
  res.send('About Page - Deployed on Railway');
});

// 监听端口（必须绑定 0.0.0.0，Railway 要求）
app.listen(port, '0.0.0.0', () => {
  console.log(`App running on port ${port}`);
});