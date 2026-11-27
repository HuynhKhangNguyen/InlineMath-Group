---
name: inline-math-control-center
description: "Điều phối job InlineMath theo file qua worker chat; quản lý scope, khóa ghi và báo cáo ngắn."
---

# InlineMath Control Center

Đọc project `AGENTS.md`, `WORKFLOW.md` và phần policy của `CONTROL_CENTER.md` một lần; chỉ tra ledger khi cần tìm worker/output. Không đọc toàn bộ lịch sử xử lý.

## Dispatch

- Mỗi exact input file có một worker chat, dùng lại cho audit/recompute/fix. Baseline thuộc manifest; các version cùng dataset chạy tuần tự. Không tự tạo thêm reviewer/subagent.
- Dùng [job contract](references/job_contract.md) để lập manifest ngắn, có source/baseline/destination chính xác và allowlist khi targeted. Không nhúng HTML, source code hay toàn bộ rules vào prompt.
- Xác nhận input, collision và dataset/global locks. Worker chịu trách nhiệm conversion, semantic decisions, validation, export và publish; control center không làm lại các bước này.
- Khi được yêu cầu tạo worker chat, tìm project bằng workspace path qua `list_projects`, không hard-code project ID. Dùng lại chat đã có; không tạo worktree nếu chưa được yêu cầu.
- Prompt: dùng `$inline-math-grouping-worker`, manifest, checkpoint path nếu resume và yêu cầu final contract. Không chép lại các instruction đã nằm trong skill.
- Default dispatch: `gpt-6-luna` / `medium` cho job ghi output; `gpt-6-luna` / `low` cho compare audit. Chỉ nâng `high` cho những câu có evidence mơ hồ. `xhigh` chỉ theo yêu cầu rõ của người dùng. Ghi và áp dụng model/thinking qua tool hỗ trợ, không chỉ qua văn bản manifest.

## Monitor và chốt

- Dùng `wait_threads`, lưu cursor, mỗi lần tối đa 8 targets; bounded wait tối đa 60 giây. Không `read_thread` lặp, không gửi steering khi trạng thái không đổi.
- Khi cần can thiệp, chỉ xem latest status, checkpoint và log liên quan; một chỉ dẫn cụ thể, không yêu cầu worker giải thích lại toàn job.
- Worker phát hiện shared defect phải trả `BLOCKED_SHARED_RULE_CHANGE`. Maintenance dùng global-exclusive, không sửa chung lúc worker đang chạy. Giữ nguyên authorization và scope của người dùng.
- Kiểm tra final contract cùng manifest, output hash và receipt một lần. Không rerun conversion, đọc raw HTML hay dựng helper song song với worker. Audit sâu chỉ khi có lỗi/evidence mới hoặc được người dùng yêu cầu.
- Báo file output/report, status, validation, số recompute/error/skip và review còn lại. Chưa hoàn tất nếu gate fail, chưa publish hoặc worker chưa có terminal contract.
