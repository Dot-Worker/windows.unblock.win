# Windows Resource Explorer

以清晰的级联选择、结构化文件信息和可追溯来源，替代长列表式 Microsoft 资源页面。中文界面，静态部署，无登录、无广告、无外部字体或前端 CDN 依赖。

## 本地使用

需要 Python 3.9+；运行自动化 JavaScript 测试需要 Node.js 20+。

```sh
python3 -m http.server 8080 --bind 127.0.0.1
```

浏览器打开 http://127.0.0.1:8080 。请通过 HTTP 服务访问，不要直接双击 HTML，浏览器可能限制本地 JSON 加载。生产环境建议 HTTPS，以支持剪贴板 API。

## 数据与边界

- 数据来源：[wangzhenjjcn/Microsoft_Resources](https://github.com/wangzhenjjcn/Microsoft_Resources)，读取其已发布的 `docs/**/data.json`，不运行原抓取程序。
- 本版本使用源提交 `f69e23f8bf478004d45abd56757674155b1ece0a`（2025-10-09）。导入时间不等于资源更新日期，也不代表数据最新。
- 原始数据存在重复条目和跨文件混合下载组。导入器尽量按文件身份归并，保留出处，不把一个文件的属性套用到另一个文件。
- 未知信息显示未知；没有校验值不生成校验值。文件名推断的语言、架构不等于实测确认。
- 下载链接、文件完整性、许可与安全性未经本项目逐一验证。来源站点不是 Microsoft 官方网站，不能把整个目录称为“微软官方认证资源”。
- HTTP/HTTPS 链接交由用户主动打开；ed2k 等链接仅供复制。网站不托管软件安装文件，不自动下载或执行安装程序，也不提供激活绕过。
- 使用软件须遵守相应产品许可。旧版本可能已停止支持，使用前应核对 Microsoft 官方生命周期信息。

## 部署

整个仓库可作为静态目录部署；所有前端资源使用相对路径，支持 GitHub Pages 项目路径。仓库提交本身不等于网站上线。

GitHub Pages 测试域名为 `msdn.unblock.win`，使用主分支根目录作为发布源。`CNAME` 仅包含此测试域名；DNS 由域名所有者维护。不改动旧站 `windows.unblock.win`，也不自动开启定时抓取任务。实际部署与 HTTPS 状态以仓库 Pages 页面和验收记录为准。

## 测试

```sh
npm test
npm run test:data
```

详情见 [验收记录](docs/ACCEPTANCE.md)。未经过的验证不标为通过。

## 版权与来源

新界面及导入器独立实现，不复制上游 Python/HTML 实现。保留上游数据出处与原始属性。
上游 README 声明 MIT，但所检查的提交没有附带 LICENSE 文件；本项目不替上游补造许可，也不声称拥有 Microsoft 产品、商标或安装文件的权利。继续公开分发数据前，应由维护者核实相关许可与来源使用条件。
