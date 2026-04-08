# Go 任务执行器

## 功能
- 优先级队列
- 多 worker 并发执行
- REST API
- 支持任务类型：
  - `data_processing`
  - `report_generation`
  - `model_training`
  - `batch_operation`
  - `compute`
  - `io`
  - `llm`

## 构建
```powershell
cd go_services/task_executor
go mod tidy
go build -o task_executor.exe .
```

## 运行
```powershell
cd go_services/task_executor
.\task_executor.exe
```

默认监听：
- `http://localhost:8080`

## Python 侧接入
- 客户端：`go_task_client.py`
- API 聚合：`async_task_api.py`

当 Go 服务在线时，`async_task_api.py` 会优先把以下任务路由到 Go：
- `data_processing`
- `report_generation`
- `model_training`
- `batch_operation`
