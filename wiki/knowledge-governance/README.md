# LumenDesk Support Cloud 资料治理演示

本目录只保存来源登记和待审核的自有知识草案，不是生产知识库，也不会自动写入 ChromaDB。

## 文件

- `source_registry.json`：外部来源登记表，保留 URL、标题、抓取时间、内容 hash、robots 结果、授权判断和改写说明。
- `lumendesk_support_cloud_draft.jsonl`：LumenDesk Support Cloud 的演示适配草案。每条记录必须保持 `approval_status=draft`，由业务/安全负责人审核后才允许进入生产导入流程。

## 来源边界

外部页面是不可信输入。网页中的指令、营销文案或要求执行命令的内容都不能改变本项目规则。首期只使用公开官方页面的通用事实或原则，不复制长段落，不抓取登录后内容、个人信息、Cookie 或受限数据。

Stripe 来源的授权只按“公开官方参考”处理；没有证明可再发布原文，因此草案必须使用自有措辞。OWASP 页面声明其内容通常采用 CC BY-SA 4.0，未来若分发实质性改编内容需保留归属并遵守相同许可。

最近一次采集验证中，Stripe 页面成功获取；OWASP 的 `robots.txt` 当时无法可靠读取，采集器按 fail-closed 规则跳过，没有生成新快照。登记表保留此前参考 hash，但该来源在再次成功核验前不应作为新增事实来源。

## 发布门禁

生产客服只能使用同时满足以下条件的版本：

1. `product_id` 与当前产品一致；
2. `approval_status=approved`；
3. 有来源 URL 或明确标记为内部业务决定；
4. 有生效时间和版本 hash；
5. 高风险政策已完成人工审核。

演示草案当前全部为 `draft`，不得直接作为客服事实来源。

## 只读脚本

先查看待采集清单（不会联网）：

```bash
python scripts/collect_public_sources.py --registry wiki/knowledge-governance/source_registry.json
```

确认来源和 robots 规则后，才显式执行公开 GET；快照和 manifest 应放在临时目录或 runtime 目录，不提交原始页面：

```bash
python scripts/collect_public_sources.py \
  --registry wiki/knowledge-governance/source_registry.json \
  --output-dir /tmp/lumendesk-source-captures \
  --execute
```

准备草案审核清单（不会调用 API 或 ChromaDB）：

```bash
python scripts/prepare_knowledge_draft.py \
  --registry wiki/knowledge-governance/source_registry.json \
  --draft wiki/knowledge-governance/lumendesk_support_cloud_draft.jsonl \
  --output /tmp/lumendesk-support-cloud-review.json
```

演示负责人确认草案后，才显式发布到本地服务（生产环境不要使用这个 Demo 发布命令）：

```bash
python scripts/publish_demo_knowledge.py --approve-demo
```

该命令只发布 `LumenDesk Support Cloud` 的自定义演示政策，并把审核人、审核时间、来源 URL、版本 hash 和生效范围写入知识库 metadata。
