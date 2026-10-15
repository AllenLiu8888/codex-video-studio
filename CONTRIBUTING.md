# 维护与扩展

先读 AGENTS.md 与相关文档。只改本次负责的 checkout；并行制作使用各自目录，重型渲染可串行。用户素材与密钥默认不纳入Git。

领域变化先改 `docs/domains.md` 对应规则和本期资料；品牌变化改项目 `brand/`，为新期冻结新版本。新增生图/语音供应商时实现独立适配器，保留实际请求、缓存指纹、未知提交状态和费用边界。不要为绕过质量问题取消审核门禁。

```bash
python3 -m unittest discover -s tests -v
python3 studio.py doctor
python3 studio.py demo --output /tmp/video-studio-review-unique
```

测试目录必须是新的或空目录。检查输出视频与本次修改相关的实际帧；音频听感、品牌审美和客户接受单独记录。改动文稿、镜头任务、参考、字体或字幕布局时，让旧审核失效并重新检查受影响部分。

公开提交前审阅 `git diff --cached` 与文件列表：不提交 `.env`、客户资料、个人路径、付费响应的临时URL、未获再分发许可的媒体。新生成结果需确认允许公开，不把生产目录整批添加。
