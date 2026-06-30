window.PKA_MOCK_DATA = {
  users: {
    primary: {
      email: "1033795760@qq.com",
      displayName: "个人知识库用户",
    },
    longEmail: {
      email: "very.long.authorized.account.name.for.prototype.review@example.knowledge.internal",
      displayName: "长邮箱测试用户",
    },
  },

  sessions: {
    planning: {
      session_id: "sess_planning",
      title: "整理家庭保险、体检和证件资料",
      created_at: "2026-06-28T09:10:00+08:00",
      updated_at: "2026-06-30T10:42:00+08:00",
      context_percent: 42,
    },
    empty: {
      session_id: "sess_empty",
      title: "新的知识库对话",
      created_at: "2026-06-30T09:00:00+08:00",
      updated_at: "2026-06-30T09:00:00+08:00",
      context_percent: 2,
    },
    longTitle: {
      session_id: "sess_long_title",
      title:
        "一个用于验证侧边栏省略号和移动端标题换行边界的超长会话标题，包含中文 English 12345",
      created_at: "2026-06-25T17:20:00+08:00",
      updated_at: "2026-06-29T21:16:00+08:00",
      context_percent: 78,
    },
    search: {
      session_id: "sess_search",
      title: "检索差旅报销规则",
      created_at: "2026-06-22T08:35:00+08:00",
      updated_at: "2026-06-27T18:04:00+08:00",
      context_percent: 28,
    },
  },

  messagesBySession: {
    sess_planning: [
      {
        role: "user",
        author: "你",
        text: "帮我整理一下医保报销材料，哪些是必须保存到知识库里的？",
      },
      {
        role: "agent",
        author: "Agent",
        text:
          "根据已保存的 Q&A，医保报销至少需要保留发票、费用明细、病历或诊断证明、身份证件和银行卡信息。下面是可追溯来源。",
        steps: ["检索 Q&A 知识库", "读取卡片 qa_medical_reimburse_001", "生成带来源回答"],
        sources: ["qa_medical_reimburse_001", "qa_identity_docs_002"],
      },
      {
        role: "user",
        author: "你",
        text: "如果只有电子发票，还需要纸质版本吗？",
      },
      {
        role: "agent",
        author: "Agent",
        text:
          "当前知识库没有保存电子发票是否必须打印的明确规则。我不能把未确认的信息当作事实回答。建议补充一条来自保险公司或医保窗口的 Q&A 后再保存。",
        steps: ["检索 Q&A 知识库", "未找到足够证据", "诚实拒答"],
        sources: [],
      },
    ],
    sess_empty: [],
    sess_long_title: [
      {
        role: "user",
        author: "你",
        text:
          "这是一条很长的用户输入，用来检查聊天气泡在桌面和移动端是否会溢出。The quick brown fox checks wrapping with code_like_tokens_and_long_identifiers.",
      },
      {
        role: "agent",
        author: "Agent",
        text:
          "这是长文本边界测试。界面应该允许内容自然换行，不挤压左右面板，不覆盖输入框，也不让操作按钮被推出可视范围。",
        steps: ["加载历史消息", "渲染长文本"],
        sources: [],
      },
    ],
    sess_search: [
      {
        role: "user",
        author: "你",
        text: "差旅报销的发票抬头是什么？",
      },
      {
        role: "agent",
        author: "Agent",
        text:
          "知识库记录显示，差旅发票抬头应使用公司全称，税号以财务系统中的最新登记为准。请以卡片来源为准核对。",
        steps: ["关键词检索", "读取差旅报销卡片"],
        sources: ["qa_travel_invoice_003"],
      },
    ],
  },

  cards: {
    medical: {
      card_id: "qa_medical_reimburse_001",
      question: "医保报销材料需要保存哪些凭证？",
      summary: "发票、费用明细、病历或诊断证明、身份证件和银行卡信息需要保留。",
      answer:
        "医保报销材料应保留医疗发票、费用明细、病历或诊断证明、身份证件、银行卡信息。不同地区可能要求补充材料。",
      category: "家庭事务",
      source_type: "manual_qa",
      keywords: ["医保", "报销", "发票", "病历"],
      created_at: "2026-06-20T19:30:00+08:00",
      updated_at: "2026-06-26T12:14:00+08:00",
      sources: [
        { name: "Q&A 卡片", detail: "qa_medical_reimburse_001", score: "事实源" },
        { name: "人工录入", detail: "PostgreSQL", score: "100%" },
      ],
    },
    identity: {
      card_id: "qa_identity_docs_002",
      question: "常用证件复印件应该如何归档？",
      summary: "身份证、户口本、银行卡复印件应按用途分组，并记录提交对象。",
      answer: "常用证件复印件应按用途分组保存，记录提交对象、提交日期和是否需要撤回或销毁。",
      category: "家庭事务",
      source_type: "manual_qa",
      keywords: ["证件", "归档", "身份证"],
      created_at: "2026-06-18T20:10:00+08:00",
      updated_at: "2026-06-18T20:10:00+08:00",
      sources: [{ name: "Q&A 卡片", detail: "qa_identity_docs_002", score: "事实源" }],
    },
    travel: {
      card_id: "qa_travel_invoice_003",
      question: "差旅报销的发票抬头是什么？",
      summary: "差旅发票抬头使用公司全称，税号以财务系统最新登记为准。",
      answer: "差旅发票抬头应使用公司全称。税号、地址和开户行以财务系统中的最新登记为准。",
      category: "工作",
      source_type: "manual_qa",
      keywords: ["差旅", "报销", "发票"],
      created_at: "2026-06-12T08:30:00+08:00",
      updated_at: "2026-06-24T16:45:00+08:00",
      sources: [
        { name: "财务 Q&A", detail: "qa_travel_invoice_003", score: "事实源" },
        { name: "人工确认", detail: "2026-06-12", score: "高" },
      ],
    },
    long: {
      card_id: "qa_extremely_long_identifier_for_layout_boundary_004_20260630",
      question:
        "一条包含非常长问题标题的知识卡片，测试右侧列表、详情页标题、复制按钮和移动端抽屉在极端内容下是否仍然可用？",
      summary:
        "该卡片只用于 UI 边界测试，包含长标题、长 card_id、长关键词和中英混排内容。",
      answer:
        "当知识卡片包含很长的问题、长 ID 或中英混排时，界面应优先保持可读性。长内容可以换行或截断，但不应遮挡操作区。",
      category: "界面测试",
      source_type: "manual_qa",
      keywords: ["layout", "overflow", "长文本", "prototype"],
      created_at: "2026-06-30T08:00:00+08:00",
      updated_at: "2026-06-30T08:15:00+08:00",
      sources: [{ name: "边界测试", detail: "manual", score: "100%" }],
    },
  },

  approvals: {
    pendingSave: {
      approval_id: "approval_save_qa_card_001",
      toolName: "save_qa_card",
      toolLabel: "保存 Q&A 卡片",
      targetLabel: "目标",
      target: "当前用户知识库",
      changes: ["新增 1 张 Q&A 卡片"],
      status: "pending",
      title: "保存新的 Q&A 卡片",
      description: "Agent 准备把用户确认的信息写入长期知识库。",
      preview: "问题：电子发票是否必须打印？答案：需要以当地医保窗口要求为准。",
      risk: "该操作会持久化到当前用户的知识库。",
    },
    deniedSave: {
      toolName: "save_qa_card",
      status: "denied",
      title: "保存已被拒绝",
      description: "用户拒绝本次持久化操作。",
      preview: "问题：电子发票是否必须打印？答案：需要以当地医保窗口要求为准。",
      risk: "未写入长期知识库。",
    },
    approvedSave: {
      toolName: "save_qa_card",
      status: "approved",
      title: "保存已通过",
      description: "工具执行完成，知识卡片已加入列表。",
      preview: "问题：电子发票是否必须打印？答案：需要以当地医保窗口要求为准。",
      risk: "已写入当前用户的知识库。",
    },
  },

  generatedAnswer: {
    userText: "请帮我保存电子发票是否需要打印这条 Q&A。",
    steps: ["识别保存意图", "准备 save_qa_card 参数", "等待用户审批"],
    answer: "我可以帮你保存，但这个操作会写入长期知识库，需要你先确认。",
  },

  errors: {
    apiError: "读取知识卡片失败，请稍后重试。",
    expired: "登录状态已失效，请重新登录。",
    loginFailed: "验证码无效或已过期。",
  },
};
