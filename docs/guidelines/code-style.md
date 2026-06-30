# 代码规范

本文档记录本仓库长期稳定的代码规范，用于约束代码新增、修改、重构和审查。

本文档只记录可复用的编码规则，不记录单次任务计划、临时实现步骤、分支安排或工作进度。

## 常量管理

业务常量必须从业务实现代码中抽离，放入所属领域目录下的 `constants.py` 文件，并通过常量类统一管理。

常量文件只承载稳定常量，不承载业务流程、运行时状态、工具函数或临时任务决策。常量应按领域就近放置；只有真正跨多个领域共享的常量，才允许放入包顶层常量文件。

业务代码使用常量时，应导入常量类并设置领域别名：

```python
from personal_knowledge_agent.apps.web.constants import WebConstants as web_constants

limit = web_constants.DEFAULT_CARD_LIMIT
```

不得在业务代码中散落具有业务含义的数字、阈值、状态值、工具名、默认值或重复字符串。

## 命名规则

常量类使用 PascalCase，并以 `Constants` 结尾，例如 `WebConstants`、`AgentRuntimeConstants`、`AuthConstants`。

常量成员使用全大写蛇形命名，例如 `DEFAULT_CARD_LIMIT`、`APPROVAL_TIMEOUT_SECONDS`、`AUTH_COOKIE_NAME`。

导入别名使用小写蛇形，并以 `_constants` 结尾，例如 `web_constants`、`runtime_constants`、`auth_constants`。

前端常量应放入专门的前端常量文件，并使用统一命名空间对象管理；常量键同样使用全大写蛇形命名。
