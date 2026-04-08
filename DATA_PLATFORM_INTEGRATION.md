# Data Platform 整合说明

## 概述

data_platform 是一个基于 Vue 3 + Vite 的风机监控可视化前端项目，已成功整合到 Agent Framework 主项目中。

## 整合内容

### 1. 静态文件部署
- 构建输出目录：`data_platform/docs/`
- 部署位置：`src/agent_framework/static/data_platform/`
- 包含内容：
  - HTML 入口文件
  - JavaScript 模块
  - CSS 样式文件
  - 3D 模型资源（GLB 格式）
  - 图片和纹理资源
  - 视频文件

### 2. Flask 路由配置

在 `src/agent_framework/web/web_ui.py` 中添加了以下路由：

```python
@app.route('/data-platform')
@app.route('/data-platform/')
def data_platform_home():
    """数据平台 - 风机监控可视化"""
    return send_file(_PKG_ROOT / 'static' / 'data_platform' / 'index.html')

@app.route('/data-platform/<path:filename>')
def data_platform_static(filename):
    """数据平台静态资源"""
    return send_from_directory(_PKG_ROOT / 'static' / 'data_platform', filename)
```

### 3. 门户页面集成

在 `src/agent_framework/templates/portal.html` 的侧边栏导航中添加了入口：

```html
<a class="..." href="/data-platform">
    <span class="material-symbols-outlined">monitoring</span>
    <span>Data Platform</span>
</a>
```

## 访问方式

启动 Agent Framework 服务后，可通过以下方式访问：

1. **直接访问**：`http://localhost:5000/data-platform`
2. **从门户进入**：`http://localhost:5000/portal` → 点击侧边栏 "Data Platform"

## 功能特性

Data Platform 提供以下功能：

- **风场地图**：基于 Leaflet 的地图展示
- **风机监控**：实时监控风机运行状态
- **AI 视频分析**：智能视频分析功能
- **3D 可视化**：基于 Three.js 的 3D 模型展示
- **数据图表**：基于 ECharts 的数据可视化

## 技术栈

### 前端技术
- Vue 3
- Vue Router
- TypeScript
- Three.js（3D 渲染）
- ECharts（图表）
- Leaflet（地图）
- GSAP（动画）
- Autofit.js（自适应布局）

### 构建工具
- Vite 5
- Rollup（打包）
- Sass（样式预处理）

## 开发说明

### 重新构建前端

如需修改 data_platform 前端代码并重新部署：

```bash
# 进入 data_platform 目录
cd data_platform

# 安装依赖（首次）
npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build

# 复制构建产物到主项目
cp -r docs/* ../src/agent_framework/static/data_platform/
```

### API 代理配置

data_platform 的 `vite.config.ts` 中配置了 API 代理：

```typescript
proxy: {
  '/api/dify': {
    target: 'http://localhost:2080/v1',
    changeOrigin: true,
    rewrite: (path) => path.replace(/^\/api\/dify/, ''),
  },
  '/api': {
    target: 'http://localhost:3001',
    changeOrigin: true,
  },
}
```

在生产环境中，这些 API 请求会直接发送到 Flask 后端，需要确保相应的 API 端点已实现。

## 注意事项

1. **资源路径**：index.html 中使用相对路径（`./`），确保在 Flask 路由下正常工作
2. **CDN 依赖**：Leaflet 地图库通过 CDN 加载，需要网络连接
3. **静态资源大小**：包含大量字体文件和 3D 模型，总大小约 10MB+
4. **浏览器兼容性**：需要现代浏览器支持 ES6+ 和 WebGL

## 目录结构

```
data_platform/
├── src/                    # 源代码
│   ├── assets/            # 静态资源（字体、图片）
│   ├── components/        # Vue 组件
│   ├── pages/            # 页面组件
│   ├── router/           # 路由配置
│   └── main.ts           # 入口文件
├── public/               # 公共资源
├── docs/                 # 构建输出（已复制到主项目）
├── vite.config.ts        # Vite 配置
└── package.json          # 依赖配置

src/agent_framework/static/data_platform/  # 部署位置
├── index.html
├── assets/               # CSS 和字体
├── js/                   # JavaScript 模块
├── images/              # 图片资源
├── models/              # 3D 模型
├── textures/            # 纹理贴图
└── videos/              # 视频文件
```

## 后续优化建议

1. **API 集成**：将 data_platform 的 API 请求对接到 Agent Framework 的后端 API
2. **权限控制**：添加访问权限验证
3. **数据对接**：连接真实的风机数据源
4. **性能优化**：考虑资源懒加载和代码分割
5. **离线地图**：考虑使用离线地图瓦片，减少对外部 CDN 的依赖
