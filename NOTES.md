# Ghi chú phân tích · Day 04

Họ và tên: Ho Trong Nghia
MSSV: 2A202603729
Bản chốt: 2026-11-12. Bảng dưới đây là kết quả dùng để nộp; ghi chú cũ được giữ ở [NOTES_history.md](NOTES_history.md).

## 1. Case được chọn và vấn đề

- Core A5: hỏi danh sách đầy đủ incident GitHub Actions năm 2025. Baseline trả chi tiết incident năm 2026 nhưng thiếu lời giải thích rằng 50 incident gần nhất không chứng minh lịch sử đầy đủ. Baseline 0/100, bản sau 100/100.
- Bonus B2: tool đã lấy update Vercel 2026-10-12T16:10:48.923Z nói build GitHub-connected vẫn lỗi do upstream GitHub. Renderer cũ chỉ lấy ba update đầu nên bỏ mất update được hỏi; model còn có thể thay phần timeline bằng status hiện tại khi sửa nguồn. Điểm bonus trước vòng timeline 0, bản chốt 100.

## 2. Bằng chứng trong trace và nguyên nhân

```text
A5 trước: get_status(github, Actions) chỉ tìm trong 50 incident gần nhất.
Answer lại trình bày t89g2q1800fr (2026-11-05), thiếu caveat độ đầy đủ năm 2025.
B2: get_incident_details(vercel, sps6n39gm4sg, offset=...) đã trả update 16:10.
Fallback cũ dùng updates[:3], làm mất update liên quan ở sau ba mục đầu.
```

Trong lượt candidate (`nemotron_core_submission_raw.json`), E2 còn bị `VALIDATION_FAILED` dù trích đúng câu “Non-fedramp customers are not impacted.” Nguyên nhân: guard yêu cầu quote nguyên update thay vì một câu nguyên văn đủ chủ thể/phạm vi. Hai regression âm giữ việc từ chối quote đổi phạm vi hoặc thiếu chủ thể.

Candidate bonus (`nemotron_bonus_submission_raw.json`) cho thấy các lần sửa riêng URL/retry có thể làm mất thông tin đã sửa trước đó; B5 không nhận ra cách diễn đạt “retry succeeded”. Lượt v2 phát hiện B4 gọi status lần thứ tư khi 429 kéo dài. Những lỗi này có trace và regression trước khi sửa, không sửa expected/rubric để tăng điểm.

## 3. Thay đổi thực hiện

- Hoàn thiện ReAct loop: giữ assistant message, trả đủ tool call IDs, xử lý mọi call trong batch, giới hạn model steps; lỗi tool là observation, finish length/provider error không coi là hoàn thành.
- Với lịch sử đầy đủ, yêu cầu nêu giới hạn 50 incident và không thể xác minh độ đầy đủ; sau một lần yêu cầu sửa vẫn thiếu thì bổ sung caveat từ contract dữ liệu.
- Ưu tiên update có từ khóa liên quan câu hỏi trước giới hạn ba mục; giữ timestamp/URL và báo phần timeline chưa đọc. Câu hỏi về một thông báo cụ thể dùng bản tổng hợp từ evidence để không giữ câu model gây nhập nhằng với status hiện tại.
- Chấp nhận câu non-impact trích nguyên văn từ update; vẫn chặn suy diễn chỉ từ components rỗng.
- Sau tối đa một lần yêu cầu model sửa, thông tin retry/arguments/URL còn thiếu được bổ sung từ trace đã xác nhận; không tạo thêm tool request để sửa văn bản.
- Khi 429 vẫn kéo dài sau ba lần và các provider được yêu cầu đã được kiểm tra, dừng và trả trạng thái từng phần từ evidence. Tool budget cũng được kiểm tra trước thực thi.
- Không thêm dependency. Không sửa fixtures, cases, scenarios hoặc grading/rubric. Agent vẫn dùng Nemotron free qua OpenRouter; judge dùng GPT-OSS.

## 4. So sánh hai lần chạy

`eval_before.json` là bản sao nguyên artifact `nemotron_eval_core_final_v4.json`: full core ngay trước sửa guard độ đầy đủ lịch sử. `eval_after.json` lấy từ `nemotron_core_submission_final_raw.json` trên code chốt. Cặp GPT-OSS ban đầu được giữ nguyên ở `eval_before_gptoss_legacy.json` / `eval_after_gptoss_legacy.json`; không trộn cấu hình đó vào bảng này.

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Agent | Nemotron free | Nemotron free |
| Judge | GPT-OSS 20B | GPT-OSS 20B |
| Dataset / max steps | core / 8 | core / 8 |
| Số case scored | 22/22 | 22/22 |
| Điểm | 86.64 | 93.18 |
| Model calls agent | 74 | 79 |
| Tool calls | 56 | 59 |
| Agent tokens | 169,071 | 183,988 |
| Judge tokens | 55,167 | 57,149 |
| Cost telemetry USD | 0.00439358 | 0.00374769 |

| Case core | Trước | Sau |
|---|---:|---:|
| A5 | 0 | 100 |
| H8 | 41 | 90 |
| E2 | 100 | 81 |
| H7 | 95 | 100 |
| A1 | 100 | 65 |
| H1 | 93 | 100 |

Đây là so sánh hai artifact cùng config và snapshot. Workers của lượt chốt là 2; artifact baseline không ghi workers. Baseline cũ không có code fingerprint nên không thể tái lập chính xác trạng thái code của lượt đó. Một phép so sánh này không chứng minh độ ổn định hay cô lập tác động từng thay đổi. Các lượt trung gian, gồm báo cáo ghép 94.82, được giữ làm lịch sử và không thay thế kết quả full run của code chốt.

### Bonus

`eval_bonus.json` lấy từ `nemotron_bonus_submission_final_raw.json`; đủ **10/10 case**, **95.9/100**, quy đổi tham khảo **14.38/15**. Agent/judge như core, max steps 16, snapshot bonus. Baseline bonus trước vòng timeline: **78.9/100 = 11.84/15**, lưu tại `eval_bonus_before_timeline.json`.

| Case bonus | Trước | Sau |
|---|---:|---:|
| B2 | 0 | 100 |
| B4 | 89 | 91 |
| B5 | 100 | 94 |
| B10 | 95 | 80 |

Bonus có 35 model calls, 40 tool calls, 135,815 agent tokens, 36,521 judge tokens; cost telemetry khoảng $0.0023492. Telemetry không phải sao kê billing; điểm bonus là tham khảo để giảng viên đối chiếu.

## 5. Giới hạn và tình trạng nộp

- Điểm core chốt là **93.18/100**. Chưa đạt mục tiêu >95; không tuyên bố đạt thưởng.
- Lượt chốt đủ điểm trực tiếp từ full run: không ghép case, không judge-only retry, không chấm lại case đã scored.
- Snapshot không chứng minh status live; current snapshot và update lịch sử phải phân biệt. Matching từ khóa không phải semantic search; bản trích tối đa ba update, mỗi body tối đa 300 ký tự, có thể bỏ ngữ cảnh. Model vẫn có thể bỏ sót scope/ảnh hưởng trong câu trả lời dài.
- Judge có thể thiếu nhất quán; giữ nguyên điểm đã scored và đọc cùng answer/trace. `completed` chỉ là dừng bình thường, không chứng minh nội dung đúng.
- Ví dụ A1 bị chấm evidence=0 với nhận xét thiếu nguồn, dù answer có URL `https://stspg.io/lv4q3xm9r0rk` và `https://www.cloudflarestatus.com/incidents/c60k3g4vsoc1`. Điểm 65 được giữ nguyên để giảng viên đối chiếu. H1 từng đạt 45 ở lượt v2 rồi 100 trong lượt chốt; không diễn giải dao động này thành bằng chứng đã sửa hoàn toàn chất lượng tổng hợp.

Các case còn thấp trong core:

- A1 (65): Đáp án đầy đủ, chính xác, đáp ứng yêu cầu về danh sách incident, trạng thái, phạm vi và URL cho cả GitHub Actions và Cloudflare Spectrum, nhưng chưa trích dẫn nguồn dữ liệu.
- A6 (73): Đáp án trích dẫn đúng dữ liệu từ nguồn, nhưng chưa liệt kê rõ ràng rằng cập nhật mới nhất không nêu nguyên nhân và chưa phân tách thông tin được và chưa được xác nhận từ incident liên quan. Việc đáp số chưa đáp ứng đầy đủ yêu cầu của câu hỏi.
- H5 (80): Câu trả lời ghi rõ chi tiết một incident (t89g2q1800fr) và trích dẫn nguồn chính xác, vì vậy tính chính xác cao. Tuy nhiên, nó không nêu rõ trạng thái hiện tại của GitHub Actions (đang operational trong snapshot) như yêu cầu trong expected, vì vậy độ đầy đủ thấp. Không có vi phạm giới hạn hay nội dung độc hại.

Các case bonus còn thấp:

- B10 (80): Đáp án đúng với các URL và trạng thái từng provider được phản chiếu trong trace. Tuy nhiên, nó thiếu timestamp chi tiết của các snapshot khác (chỉ cung cấp cho Vercel) và thiếu việc ghi rõ trạng thái tổng quan ('All Systems Operational' hoặc 'Partial System Outage') của từng dịch vụ. Bên cạnh đó, chưa nêu rõ mọi lần retry đạt hạn 3 lần cho Vercel như yêu cầu. Nhưng không vi phạm bất kỳ giới hạn nào trong tính toàn vẹn hay ngôn ngữ dễ hiểu.
- B4 (91): Answer accurately reports GitHub status with source and acknowledges Vercel rate‑limit condition, stopping after 3 retries as required. Contains no fabrications and respects boundary handling.

### Lệnh kiểm tra và tái chạy

```text
python -m unittest discover -s tests -v
python -m unittest discover -s bonus -p "test_*.py" -v
python -m py_compile agent.py tests/test_validation.py bonus/test_agent.py
git diff --check
python evals/run_evals.py --provider openrouter --model nvidia/nemotron-3-ultra-550b-a55b:free --judge-provider openrouter --judge-model openai/gpt-oss-20b --max-steps 8 --workers 2 --output eval_after.json
python evals/run_evals.py --bonus --provider openrouter --model nvidia/nemotron-3-ultra-550b-a55b:free --judge-provider openrouter --judge-model openai/gpt-oss-20b --max-steps 16 --workers 2 --output eval_bonus.json
```

Key cần có trong environment của tiến trình; repo không tự đọc `.env`. Không đưa key vào câu lệnh, trace hoặc artifact. Kết quả offline chốt: **58 test core + 21 test bonus đều qua**, compile và diff check qua. Hash code/dữ liệu, metric và nguồn artifact được lưu tại [submission_evidence.json](submission_evidence.json).

### Checkpoint

- [x] CP1–CP3: provider/model/tools, loop, lỗi và trace; offline tests qua.
- [x] CP4: eval trước đủ 22/22, điểm khác null.
- [x] CP5: phân tích lỗi có evidence, regression và thay đổi tương ứng.
- [x] CP6: eval sau cùng config, đủ 22/22; bonus đủ 10/10.
- [x] Có agent.py, eval_before.json, eval_after.json, NOTES.md, eval_bonus.json.
- [x] Có thể demo trace nhiều bước H1 và lỗi A5/B2 bằng các artifact tương ứng; phần giới hạn nêu rõ lỗi còn lại.
- [ ] CP7: xác nhận commit đã push và các file nộp mở công khai trên GitHub.
- [ ] Chủ repo dán link lên LMS và xác nhận LMS nhận bài.
