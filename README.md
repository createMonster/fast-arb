# 🚀 Funding Rate Arbitrage MVP

一个专注于资金费率套利的MVP项目，主要在Reya Network和Hyperliquid之间寻找套利机会。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## ✨ 核心功能

### 🔍 资金费率监控
- 实时监控Reya Network和Hyperliquid的资金费率
- 计算资金费率价差
- 识别套利机会
- WebSocket实时数据流

### 📊 价差计算与分析
- 实时计算两个交易所之间的资金费率差异
- 考虑交易费用和滑点
- 评估套利机会的盈利潜力
- 智能风险评估

### 🎯 套利机会识别
- 基于配置的阈值识别有效套利机会
- 风险评估和头寸规模计算
- 机会优先级排序
- 置信度评分

### ⚡ 自动交易执行
- 支持模拟模式和实盘交易
- 同时在两个交易所执行对冲交易
- 实时监控订单状态
- 智能执行策略

### 🛡️ 风险管理
- 最大仓位限制
- 止损止盈设置
- 实时风险监控
- 紧急停止功能

## 🏢 支持的交易所

### Reya Network
- ✅ 使用官方Python SDK连接
- ✅ 支持WebSocket实时数据
- ✅ 永续合约交易
- ✅ 高性能执行

### Hyperliquid
- ✅ 使用CCXT库连接
- ✅ 实时资金费率获取
- ✅ 永续合约交易
- ✅ 低延迟API

## 项目结构

```
fast-arb/
├── README.md                 # 项目文档
├── requirements.txt          # Python依赖
├── config/
│   ├── config.yaml          # 主配置文件
│   └── trading_pairs.yaml   # 交易对配置
├── src/
│   ├── __init__.py
│   ├── main.py              # 主程序入口
│   ├── config/
│   │   ├── __init__.py
│   │   └── config_manager.py # 配置管理
│   ├── exchanges/
│   │   ├── __init__.py
│   │   ├── base_exchange.py  # 交易所基类
│   │   ├── reya_client.py    # Reya客户端
│   │   └── hyperliquid_client.py # Hyperliquid客户端
│   ├── arbitrage/
│   │   ├── __init__.py
│   │   ├── funding_monitor.py # Funding rate监控
│   │   ├── opportunity_detector.py # 套利机会检测
│   │   └── trade_executor.py # 交易执行
│   └── utils/
│       ├── __init__.py
│       ├── logger.py         # 日志工具
│       └── helpers.py        # 辅助函数
├── tests/
│   ├── __init__.py
│   └── test_arbitrage.py
└── logs/                     # 日志目录
```

## 🚀 快速开始

### 1. 环境要求
- Python 3.11+
- pip 或 conda
- Git

### 2. 安装

```bash
# 克隆项目
git clone <repository-url>
cd fast-arb

# 快速设置开发环境
make dev-setup

# 或手动安装
pip install -r requirements.txt
cp .env.example .env
```

### 3. 配置

编辑 `.env` 文件，添加你的API密钥：

```bash
# Reya Network
REYA_PRIVATE_KEY=your_reya_private_key_here
REYA_RPC_URL=https://rpc.reya.network
REYA_WS_URL=wss://ws.reya.network

# Hyperliquid
HYPERLIQUID_PRIVATE_KEY=your_hyperliquid_private_key_here
HYPERLIQUID_TESTNET=true

# General Settings
LOG_LEVEL=INFO
SIMULATION_MODE=true
```

### 4. 测试连接

```bash
# 检查配置
make check-config

# 测试交易所连接
make test-connections

# 查看当前价差
make check-spreads
```

### 5. 运行

```bash
# 监控模式（安全，不交易）
make monitor
# 或
python main.py run --monitor-only

# 交易模式（实际交易）
make run
# 或
python main.py run
```

## ⚙️ 配置说明

### 主配置文件 (config/config.yaml)

```yaml
general:
  log_level: "INFO"
  update_interval: 5  # 数据更新间隔(秒)
  simulation_mode: true  # 模拟模式

# 交易所配置
reya:
  rpc_url: "https://rpc.reya.network"
  ws_url: "wss://ws.reya.network"
  private_key: "${REYA_PRIVATE_KEY}"  # 从环境变量读取

hyperliquid:
  testnet: true
  private_key: "${HYPERLIQUID_PRIVATE_KEY}"

# 套利策略配置
arbitrage:
  min_spread_threshold: 0.1  # 最小价差阈值(%)
  max_spread_threshold: 2.0  # 最大价差阈值(%)
  check_interval: 10  # 检查间隔(秒)

# 风险管理
risk_management:
  max_total_position: 10000  # 最大总仓位($)
  max_position_per_pair: 5000  # 单交易对最大仓位($)
  min_trade_amount: 100  # 最小交易金额($)
  stop_loss_percentage: 5.0  # 止损百分比
  take_profit_percentage: 2.0  # 止盈百分比

# 交易对配置
trading_pairs:
  SOL-USD:
    reya_symbol: "SOL-USD"
    hyperliquid_symbol: "SOL"
    min_funding_rate_diff: 0.05  # 最小资金费率差异(%)
    max_position_size: 1000  # 最大仓位大小
  ETH-USD:
    reya_symbol: "ETH-USD"
    hyperliquid_symbol: "ETH"
    min_funding_rate_diff: 0.05
    max_position_size: 2000
  BTC-USD:
    reya_symbol: "BTC-USD"
    hyperliquid_symbol: "BTC"
    min_funding_rate_diff: 0.05
    max_position_size: 3000
```

## 📊 使用示例

### 监控模式
```bash
# 启动监控，查看实时价差
python main.py run --monitor-only

# 检查特定交易对的价差
python main.py check-spreads --pair SOL-USD

# 查看配置
python main.py config-check
```

### 交易模式
```bash
# 启动自动套利（请谨慎使用）
python main.py run

# 使用自定义配置文件
python main.py run --config custom_config.yaml
```

## 🧪 测试

```bash
# 运行所有测试
make test

# 运行单元测试
make test-unit

# 运行集成测试
make test-integration

# 生成覆盖率报告
make test-coverage
```

## 🛠️ 开发指南

### 项目结构
```
fast-arb/
├── src/
│   ├── config/          # 配置管理
│   ├── exchanges/       # 交易所客户端
│   ├── arbitrage/       # 套利核心逻辑
│   └── utils/           # 工具函数
├── tests/               # 测试文件
├── config/              # 配置文件
├── logs/                # 日志文件
└── docs/                # 文档
```

### 添加新交易所
1. 在 `src/exchanges/` 下创建新的客户端类
2. 继承 `BaseExchange` 抽象类
3. 实现所有必需的方法
4. 在 `__init__.py` 中注册新交易所

### 代码规范
```bash
# 代码格式化
make format

# 代码检查
make lint

# 类型检查
make type-check
```

## 🐳 Docker 部署

### 单容器部署
```bash
# 构建镜像
docker build -t fast-arb .

# 运行容器
docker run -d --name fast-arb \
  --env-file .env \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  fast-arb
```

### Docker Compose 部署
```bash
# 启动所有服务（包括监控）
docker-compose up -d

# 查看日志
docker-compose logs -f arbitrage

# 停止服务
docker-compose down
```

## 📈 监控和日志

### 日志文件
- `logs/arbitrage.log` - 主要应用日志
- `logs/trades.log` - 交易执行日志
- `logs/errors.log` - 错误日志

### 监控面板
如果使用 Docker Compose，可以访问：
- Grafana: http://localhost:3000 (admin/admin)
- Prometheus: http://localhost:9090

## 🔧 故障排除

### 常见问题

**连接失败**
```bash
# 检查网络连接
ping rpc.reya.network

# 验证API密钥
python main.py test-connections
```

**配置错误**
```bash
# 验证配置文件
python main.py config-check

# 检查环境变量
env | grep REYA
env | grep HYPERLIQUID
```

**性能问题**
```bash
# 查看系统资源
make monitor-performance

# 分析日志
tail -f logs/arbitrage.log
```

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## ⚠️ 风险提示

**重要警告**：
- 本项目仅供学习和研究使用
- 加密货币交易存在高风险，可能导致资金损失
- 在使用真实资金前，请充分测试和理解代码
- 建议先在测试网络上运行
- 请遵守当地法律法规

## 📞 支持

如有问题或建议，请：
- 提交 [Issue](../../issues)
- 查看 [Wiki](../../wiki)
- 联系开发团队

---

**免责声明**: 本项目的开发者不对使用本软件造成的任何损失承担责任。用户应当自行承担使用风险，并在充分了解相关风险的前提下使用本软件。

## 后续扩展计划

- 支持更多交易所
- 添加其他类型的套利策略
- 优化执行速度和延迟
- 增加更多风险管理功能
- 添加Web界面监控