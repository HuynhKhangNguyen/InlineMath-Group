---
name: inline-math-grouping-worker
description: "Xử lý một file InlineMath theo manifest, dùng script và checkpoint; chỉ đưa quyết định ngữ nghĩa cần thiết vào model."
---

# InlineMath Grouping Worker

Một exact `inputPath`, một worker chat; audit, recompute, validation và publish ở đây. Không dispatch thêm agent/chat.

## Load và preflight

- Đọc project `AGENTS.md`, `WORKFLOW.md`, `GOAL.md`, `RULES.md`, `VALIDATION.md` một lần theo hash. Chỉ đọc phần operation tương ứng trong [execution modes](references/execution_modes.md). Resume từ checkpoint đã xác minh; không đọc lại toàn bộ tài liệu/lịch sử.
- Manifest cần job/dataset/operation/workspace/source/destination chính xác; targeted cần explicit allowlist. Xác minh baseline thực tế có chỉnh sửa tay, khóa ghi và output chưa tồn tại.
- Default: `gpt-6-luna` / `medium` cho writer, `/ low` cho compare. Record runtime thực tế; nếu legacy settings khác, báo control center áp dụng cấu hình trước compute tiếp theo. Không tự giả lập đổi model qua prompt. `high` cho affected ambiguous cases; `xhigh` chỉ khi người dùng yêu cầu.
- Hash source/baseline/engine/rules và tạo staging riêng. Không thay source hoặc output cũ; không quyền admin.

## Execute

- Dùng entrypoint/builder/verifier hiện có theo `WORKFLOW.md`. Script xử lý Excel, matching, merge, metrics, hashing và report; model quyết định context một lần trên phần recompute.
- Dùng `scripts/job_context.py packet` để chia review theo scope. Đọc tóm tắt trước; đọc full source của câu mơ hồ khi cần, không dump toàn workbook vào chat. Flags không tự chứng minh semantic PASS. Kiểm tra nghĩa của mọi câu recompute trước khi chốt.
- Context có thể là câu kể, câu hỏi, phép toán, tiêu đề, ảnh hoặc hướng dẫn. Tìm nguồn gần nhất đủ nghĩa trong stem/part; tách prompts độc lập, giữ cùng equation phụ thuộc. Không kết luận thiếu context chỉ vì ảnh alt rỗng.
- `FIB_Numberline` luôn skip cả câu; protected/nested/outside-layout phải hạch toán riêng. Targeted/incremental giữ conversion của câu ngoài scope và chỉnh sửa tay, ngoài mandatory numberline skip được khai báo.
- Checkpoint theo stage với các dependency hash. Chạy full tests khi shared implementation đổi, không mỗi file. Structural, semantic và saved-file gates vẫn bắt buộc; chỉ rerun phần bị invalidated.
- Không sửa shared `src/`, scripts/tests/rules/skills. Thiếu capability hoặc shared defect: lưu evidence nhỏ, trả `BLOCKED_SHARED_RULE_CHANGE`; không dựng lại pipeline riêng cho job.

- Mọi ID grouping mới (local wrapper/shared heading/image) phải ở phần tử con bên trong đúng `question-stem-content`, không trên chính stem hoặc ngoài nó. Context toàn stem dùng wrapper bên trong. Chỉ áp dụng cho scope xử lý lần tới, không migrate kết quả giữ lại hoặc file cũ.

## Final

Lưu final contract vào JSON và trả ngắn: job identity/status, model/thinking thực tế, source/engine/rule hashes, output/report/receipt paths, counts, review rows/UIDs, validation, `sharedFilesChanged: false`, ghi chú có ý nghĩa. Dùng đúng một schema đã có, không thiết kế lại report.

- `DONE`: gates pass, không còn semantic uncertainty.
- `NEEDS_REVIEW`: release gates pass, uncertainty được phân loại đầy đủ; tách review cũ ngoài scope.
- `BLOCKED_SHARED_RULE_CHANGE`: thiếu/sai shared logic.
- `FAILED`: validation hoặc publication thất bại.
- `BLOCKED`: thiếu scope/source/permission cần thiết.
