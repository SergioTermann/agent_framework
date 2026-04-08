import express from 'express';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import cors from 'cors';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3001;

// 数据文件路径
const DATA_DIR = path.join(__dirname, '../public/data');
const DATA_FILE = path.join(DATA_DIR, 'component-data.json');
const TOOL_DATA_FILE = path.join(DATA_DIR, 'tool-data.json');

// 确保数据目录存在
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

// 中间件
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// 读取组件数据
app.get('/api/component-data.json', (req, res) => {
  try {
    if (fs.existsSync(DATA_FILE)) {
      const data = fs.readFileSync(DATA_FILE, 'utf8');
      res.json(JSON.parse(data));
    } else {
      res.json({});
    }
  } catch (error) {
    console.error('读取数据失败:', error);
    res.status(500).json({ error: '读取数据失败' });
  }
});

// 保存组件数据
app.post('/api/save-component-data', (req, res) => {
  try {
    const { allData } = req.body;
    
    // 保存到文件
    fs.writeFileSync(DATA_FILE, JSON.stringify(allData, null, 2), 'utf8');
    
    console.log('组件数据已保存到:', DATA_FILE);
    res.json({ success: true, message: '保存成功' });
  } catch (error) {
    console.error('保存数据失败:', error);
    res.status(500).json({ error: '保存数据失败' });
  }
});

// 读取工具数据
app.get('/api/tool-data.json', (req, res) => {
  try {
    if (fs.existsSync(TOOL_DATA_FILE)) {
      const data = fs.readFileSync(TOOL_DATA_FILE, 'utf8');
      res.json(JSON.parse(data));
    } else {
      res.json({});
    }
  } catch (error) {
    console.error('读取工具数据失败:', error);
    res.status(500).json({ error: '读取工具数据失败' });
  }
});

// 保存工具数据
app.post('/api/save-tool-data', (req, res) => {
  try {
    const { allData } = req.body;
    
    // 保存到文件
    fs.writeFileSync(TOOL_DATA_FILE, JSON.stringify(allData, null, 2), 'utf8');
    
    console.log('工具数据已保存到:', TOOL_DATA_FILE);
    res.json({ success: true, message: '保存成功' });
  } catch (error) {
    console.error('保存工具数据失败:', error);
    res.status(500).json({ error: '保存工具数据失败' });
  }
});

app.listen(PORT, () => {
  console.log(`API 服务器运行在 http://localhost:${PORT}`);
  console.log(`数据文件位置: ${DATA_FILE}`);
});
