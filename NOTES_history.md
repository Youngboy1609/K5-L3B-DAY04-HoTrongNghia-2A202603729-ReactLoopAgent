# Ghi chú phân tích · Day 04

Họ và tên: Ho Trong Nghia
MSSV: 2A202603729

## 1. Case được chọn

- ID: H7
- Yêu cầu: kiểm tra GitHub Actions và Cloudflare Spectrum; timeout không được xem là trạng thái operational.
- Điểm: `eval_before.json` **55** → `eval_after.json` **100**.
- Evidence ở lần chạy đầu: tool GitHub trả `overall.indicator = none`, component Actions `operational`; tool Cloudflare trả `TimeoutError`. Dù vậy, agent viết: “when a Cloudflare status request cannot be completed, we treat the service as operational”.
- Evidence ở lần chạy sau: cùng loại timeout Cloudflare; câu trả lời nêu “the request timed out” và “I don’t have confirmed status information”. Không suy đoán trạng thái Cloudflare.

## 2. Bằng chứng trong trace

Trích yếu từ `eval_before.json`, case H7:

```text
get_status(provider=cloudflare, component=Spectrum) -> TimeoutError
Final answer -> “we treat the service as operational”
```

Trích yếu từ `eval_after.json`, case H7:

```text
get_status(provider=cloudflare, component=Spectrum) -> TimeoutError
Final answer -> “request timed out”; “status ... cannot be confirmed”
Score: 100
```

Nguyên nhân là model đã biến thiếu dữ liệu do timeout thành khẳng định operational, trái với evidence trong tool result.

## 3. Thay đổi đã thực hiện

- Hoàn thiện ReAct loop trong `agent.py`: giữ nguyên assistant message, trả đúng tool call IDs, xử lý mọi tool call, giới hạn model steps, trace lỗi/tool/usage và không coi output bị cắt là hoàn thành.
- Hỗ trợ `tools.schemas` và `tools.system_prompt` cho bonus; kiểm tra tên tool theo schema và sửa đúng hậu tố ` <|channel|>commentary` mà OpenRouter model đôi lúc gắn nhầm vào tên tool.
- Thêm hướng dẫn và validation để không suy luận operational/outage sau timeout hoặc 429; khi retry khôi phục thành công thì nêu lần lỗi ban đầu, timestamp và nguồn.
- Bắt buộc câu trả lời có URL incident đã nhận từ tool; yêu cầu đọc chi tiết incident khi câu hỏi cần phạm vi/timeline; không suy ra “không bị ảnh hưởng” chỉ vì `components` rỗng.
- Chặn câu trả lời rỗng và giới hạn mỗi validation chỉ yêu cầu sửa lại một lần, tránh tiêu hết budget vào cùng một lời nhắc.
- Khi model bỏ qua tool và tiếp tục trả rỗng, agent tự gọi status/incident detail còn thiếu theo schema; nếu model vẫn rỗng thì dựng câu trả lời từ tool results đã quan sát. Timeout được ghi là chưa xác nhận, không bị biến thành Operational.
- Nếu status bị 429 và model không tự retry, agent thử lại trong giới hạn tối đa ba lần gọi cùng provider; câu fallback nêu rõ khi retry thành công.
- Thêm regression tests trong `tests/test_validation.py`, `tests/test_lab.py` và `bonus/test_agent.py` cho các lỗi trên.
- Không sửa fixtures, eval cases/scenarios, grading hoặc rubric.

## 4. So sánh các lần chạy

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---:|---:|
| Cấu hình agent/judge | OpenRouter `openai/gpt-oss-20b` / cùng model | Giữ nguyên |
| Max steps / dataset | 8 / core | 8 / core |
| Điểm tổng | 91.91/100 | 89.36/100 |
| Case H7 | 55 | 100 |
| Case đã chấm | 22/22 | 22/22 |
| Agent model calls | 75 | 74 |
| Tool calls | 52 | 50 |
| Agent tokens | 113,836 | 131,817 |
| Judge tokens | 56,845 | 47,732 |
| Cost telemetry agent + judge | ~$0.00631 | ~$0.00703 |

Lượt baseline có một số case lỗi hạ tầng được chạy riêng một lần và ghép bằng kết quả đã chấm cùng cấu hình để đủ 22 case; lượt after cuối đủ 22 case ngay trong lần chạy. Cost là telemetry do provider trả về, không phải sao kê billing.

Lượt bonus GPT-OSS trước khi đổi agent model (được giữ lại tại `eval_bonus_gptoss_legacy.json`) dùng OpenRouter `openai/gpt-oss-20b` cho agent và judge, max steps 16:

- Điểm: **90.5/100 = 13.57/15**, đủ 10/10 case.
- B1, B3, B5, B6 và B8 đạt 100; B4 90; B7 100; B9 65; B10 50.
- B10 trace xác nhận đã gọi cả năm status tools, gồm lần retry Vercel sau 429. Câu trả lời cuối chỉ tóm tắt Vercel nên judge giảm completeness/evidence.
- Bonus usage: 48 agent calls, 33 tool calls, 125,917 agent tokens; 31,232 judge tokens. Cost telemetry agent + judge khoảng **$0.00429**.

Lượt core cuối có H7=100, nhưng tổng 89.36 thấp hơn baseline do điểm dao động ở case khác, đặc biệt A1=0, E6=30 và H4=75. Vì vậy chưa đạt mốc eval >95. Không retry các case đã có điểm chỉ để tìm điểm cao hơn.

### Chẩn đoán riêng với Nemotron free

Các lượt dưới đây chỉ chạy từng case để xác nhận lỗi cụ thể sau khi đổi model; **không phải điểm toàn bộ eval và không thay thế** `eval_before.json`/`eval_after.json`/`eval_bonus.json`:

| Case | Kết quả | Bằng chứng và kết luận |
|---|---:|---|
| A1 | 100/100 | Model dừng rỗng và không gọi tool. Agent tự lấy status GitHub + Cloudflare, chọn incident Actions đã resolved và Spectrum đang monitoring, lấy scope/URL từ detail tools rồi tổng hợp từ kết quả thật. |
| E6 | Unscored | Agent trả `github: chưa xác nhận được trạng thái (TimeoutError).` đúng yêu cầu. Judge trả rỗng (`NoneType ... strip`), nên không có điểm; đây không phải điểm 0 hay kết quả agent sai. |
| B10 | 100/100 | Agent gọi đủ năm status tools; Vercel bị 429 giả lập lần đầu, retry thành công lần hai. Câu trả lời nêu timestamp/source riêng và giới hạn retry. |

Phân tích E6: trước sửa, timeout + câu trả lời model rỗng kết thúc bằng `VALIDATION_FAILED`. Nguyên nhân là agent chỉ hỏi model viết lại, không có final fallback từ evidence và không lưu lỗi status để trình bày. Regression test mới xác nhận timeout được báo là chưa xác nhận. B10 trước sửa chỉ có một lần gọi Vercel nếu model bỏ cuộc; fallback retry có giới hạn giải quyết điểm này.

Một lượt thử core Nemotron ban đầu đã dừng trước khi hoàn tất: E1–E3 đều unscored, E4 không trả kết quả trong nhiều phút; runner chưa ghi artifact tổng. Đây là dữ liệu lịch sử, đã có các lượt full mới hơn ở mục 6. Kiểm tra offline hiện tại: core 52/52 và bonus 16/16.

## 5. Giới hạn

- Judge mặc định dùng cùng model với agent; điểm là ước lượng và có thể thiên lệch hoặc dao động giữa các lần gọi. H4 cũng cho thấy chất lượng đầu ra thơ tiếng Việt biến động.
- Snapshot là dữ liệu cố định, không chứng minh tình trạng live. Một lần chạy mỗi phiên bản không đo được độ ổn định.
- Lượt core Nemotron đầy đủ mới nhất đạt 92.41/100; vì vậy mốc >95 chưa đạt. E5 phải chấm lại judge-only một lần do GPT-OSS trả JSON lỗi; cùng answer/trace sau đó được chấm 84.
- Eval >95 chưa đạt; không nên tuyên bố đã đạt giải hoặc điểm đó được đảm bảo.
- Trước khi nộp, rà thông tin nhạy cảm trong trace/eval artifacts.

## 6. Cập nhật cuối · 2026-11-12

- Agent: OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free`; judge: OpenRouter `openai/gpt-oss-20b`; fixtures/cases/rubric không bị sửa.
- Core full run: [`nemotron_eval_core_final.json`](nemotron_eval_core_final.json), 22/22 case, **92.41/100**. E5 judge-only retry được lưu riêng trong [`nemotron_eval_core_final_v3_rejudged.json`](nemotron_eval_core_final_v3_rejudged.json); artifact `nemotron_eval_core_final.json` là lượt full sau sửa A6 và đạt 22/22.
- Ở thời điểm ghi chú ban đầu, bonus full run gần nhất có artifact là [`nemotron_eval_bonus_final_v2.json`](nemotron_eval_bonus_final_v2.json), 10/10 case, **86.9/100 = 13.04/15**. B2 đạt 93 (lượt trước 44), B6 đạt 80 (lượt trước 28); B5=20 vì lúc đó retry chỉ được cài ở đường model-issued tool call. Kết quả cập nhật sau đó ở mục “Kết quả loop cuối”.
- Bổ sung retry một lần cho lỗi offset/limit trong đường validation fallback và regression test mô phỏng đúng tình huống model rỗng. Ở thời điểm đó, một lượt full bonus mới hơn đã in B5=55, B6=96 nhưng bị dừng ở B3 sau hơn 6 phút chờ provider; runner chưa ghi artifact, nên không tính aggregate. Không dùng partial mean làm điểm bonus. Kết quả 86.9/100 là artifact full gần nhất tại thời điểm ghi chú ban đầu; các lượt đầy đủ sau đó được ghi tại “Kết quả loop cuối”.
- Sửa A6: chỉ coi cụm “latest/newest incident” là yêu cầu incident mới nhất; “latest update” của incident ID tường minh không được đổi sang incident khác. Core full sau sửa đạt A6=100.
- H4 cho thấy độ dao động của Nemotron: targeted run từng được 70, các lượt core full sau là 0 và 15. Không hard-code nội dung thơ hoặc lặp case để săn điểm.
- Cập nhật bonus còn thêm đọc trang timeline kế tiếp khi được hỏi update cụ thể, và xác minh incident mới nhất theo timestamp. Retry/pagination được thực hiện sau khi đã trả tool result cho mọi call trong batch gốc. Xác minh offline cuối: core **52/52**, bonus **16/16**, `py_compile` và `git diff --check` đều qua.
- Mốc >95 **chưa đạt**. Tại thời điểm ghi chú ban đầu, lượt core đầy đủ hợp lệ gần nhất là 92.41/100; kết quả bonus cập nhật sau đó được ghi riêng ở mục “Kết quả loop cuối”.

### Kết quả loop cuối · 2026-11-12

- Lượt bonus full `nemotron_eval_bonus_final_v3.json` ban đầu không có key trong tiến trình, vì repo không tự nạp `.env`; artifact unscored này đã bỏ. Sau khi truyền key từ `.env` vào môi trường tiến trình mà không in key, chạy full bonus tuần tự với Nemotron agent, GPT-OSS judge, max steps 16.
- Lượt trước sửa đạt 82.1/100 nhưng B5 trace cho thấy đường fallback đã nhận `INVALID_ARGUMENTS`, sửa offset/limit và lấy incident thành công; model trả rỗng, khiến câu trả lời dựng từ evidence kết thúc trước khi thông báo lần phục hồi. Regression test mới tái hiện chính xác nhánh này; sau đó fallback thêm một câu ghi nhận phục hồi từ tool evidence.
- Sau sửa: bộ offline core **52/52**, bonus **17/17**, `py_compile` và `git diff --check` qua. Lượt bonus full mới chấm 8/10 trước khi hoàn tất; B8 lỗi JSON judge và B9 judge thiếu explanation. Chấm lại **chỉ judge**, mỗi case một lần trên cùng result/trace, cho 10/10 và **78.9/100 = 11.84/15**. Artifact nộp được cập nhật tại [`eval_bonus.json`](eval_bonus.json); bản raw trước judge-only retry là [`nemotron_eval_bonus_final_v4.json`](nemotron_eval_bonus_final_v4.json), bản đã chấm lại là [`nemotron_eval_bonus_final_v4_rejudged.json`](nemotron_eval_bonus_final_v4_rejudged.json).
- B5 tăng lên **100** ở lượt sau sửa, khớp mục tiêu thay đổi. B2 tiếp tục **0**: trace đã chứa update Vercel lúc 2026-10-12 16:10 UTC trong trang offset 2, nhưng final answer vẫn bỏ nội dung đó. Đây là lỗi tổng hợp câu trả lời của model, không phải thiếu tool evidence. Không lặp eval để săn điểm; nếu tiếp tục loop, cần thiết kế regression tổng quát cho yêu cầu hỏi về một update cụ thể trong timeline.
- Điểm bonus dao động giữa các lượt; dùng artifact được chọn và reason/trace để báo cáo, không diễn giải chênh lệch như bằng chứng chắc chắn về xu hướng. Core full Nemotron gần nhất vẫn **92.41/100, 22/22**; thay đổi cuối chỉ ở nhánh bonus fallback nên core chưa chạy lại sau thay đổi này.

## 7. Kế hoạch loop cải tiến và checkpoint nộp

### Đánh giá kết quả hiện tại

- Core Nemotron **92.41/100, 22/22 case**: kết quả tốt và hợp lệ để phân tích, nhưng còn thiếu 2.59 điểm so với mục tiêu >95. Điểm thấp tập trung ở H4=15, A2=83, H7=82, E2=85 và A7=91. Đây là thứ tự ưu tiên điều tra, không phải lý do để hard-code case.
- Bonus Nemotron gần nhất có artifact **78.9/100, 10/10 case**. B5 đã lên 100 sau khi fallback nêu rõ phục hồi INVALID_ARGUMENTS; B2 vẫn 0 dù evidence update đã có trong tool trace.
- So sánh `eval_before.json` → `eval_after.json` là cùng cấu hình GPT-OSS, **91.91 → 89.36**; nó hợp lệ cho so sánh đó, nhưng không chứng minh Nemotron đã cải thiện so với baseline Nemotron. Không gộp các model/judge/config khác nhau thành một phép so sánh.
- Kết luận: chất lượng agent đã khá tốt, core và bonus đều chấm đủ case ở lượt hợp lệ gần nhất; mục tiêu >95 và checkpoint nộp cuối vẫn chưa hoàn tất. Điểm thấp của một case cần đọc cùng trace, lỗi tool, reason của judge và regression test; điểm đơn lẻ không chứng minh nguyên nhân.

### Bounded improvement loop

Mỗi vòng chỉ xử lý một lỗi có bằng chứng, không retry lặp để săn điểm:

1. **Đóng băng phép so sánh:** ghi commit/tree version, agent model Nemotron, judge GPT-OSS, dataset/snapshot, max steps (core 8, bonus 16), workers và thời điểm chạy. Giữ các điều kiện giống nhau giữa baseline và candidate. Nếu cần tuyên bố before/after cho Nemotron, phải có baseline Nemotron chạy trên phiên bản trước; không dùng cặp GPT-OSS thay thế.
2. **Chẩn đoán một case/root cause:** đọc answer, tool trace, mechanical checks và `grade.reason`; phân loại lỗi là logic agent, lựa chọn/gọi tool, chất lượng model, lỗi provider hay judge. Chọn lỗi có tác động hệ thống và bằng chứng tái hiện. Không sửa fixtures, eval cases, scenario, grading hay rubric.
3. **Tạo regression trước khi sửa:** thêm test nhỏ tái hiện nguyên nhân, rồi sửa tối thiểu trong agent. Chạy bộ offline core và bonus; chỉ chạy targeted live case một lần nếu cần xác nhận tương tác provider.
4. **Checkpoint full eval:** sau một thay đổi có lý do, chạy đúng một lượt core và một lượt bonus đầy đủ với cấu hình đã đóng băng. Chấp nhận kết quả chỉ khi core 22/22 và bonus 10/10 đều được chấm, không có score null, và artifact chứa cấu hình/điểm/trace. Judge JSON lỗi chỉ được judge-only re-evaluate cùng answer/trace tối đa một lần; không chạy lại toàn bộ chỉ vì điểm dao động.
5. **Quyết định dừng:** giữ sửa đổi nếu regression được giải quyết, test qua và không có suy giảm đáng kể ở case liên quan. Dừng loop khi core >95 và bonus đủ 10/10, hoặc sau tối đa hai vòng có căn cứ mà không còn lỗi hệ thống đáng sửa/điểm tăng không đáng kể. Nếu không đạt >95, báo đúng điểm và giới hạn; không tuyên bố đạt thưởng.

### Submission checkpoint

- [x] Có `agent.py`, `eval_before.json`, `eval_after.json`, `NOTES.md`; có artifact bonus `eval_bonus.json`.
- [x] Before/after GPT-OSS đều dùng core, max steps 8, chấm đủ 22/22; khác biệt và giới hạn đã ghi ở trên.
- [x] Có kết quả Nemotron core 22/22 và bonus 10/10; bonus nộp khớp model đã chọn và phiên bản agent có sửa fallback.
- [x] Bộ offline core 52/52, bonus 17/17; `py_compile` và `git diff --check` qua sau thay đổi cuối.
- [x] `.env` không nằm trong tracked files; đã quét 34 JSON artifacts với các pattern API key phổ biến, không có match. Vẫn cần rà nội dung nhạy cảm khác trước khi push.
- [x] Điền họ tên và MSSV ở đầu file này theo tên repo.
- [x] Chọn artifact: `eval_before.json`/`eval_after.json` là cặp GPT-OSS cùng cấu hình; `eval_bonus.json` là full bonus Nemotron agent + GPT-OSS judge; core Nemotron bổ sung nằm ở `nemotron_eval_core_final.json`.
- [x] Link repo GitHub mở được khi chưa đăng nhập.
- [ ] Rà toàn bộ artifacts nhạy cảm, commit/push các file được chọn và mở lại link để xác nhận nội dung sau push. Chưa có push nào được thực hiện.
- [ ] Nộp link repository trên LMS và xác nhận LMS nhận bài; đây là thao tác cuối của chủ repo.

**Trạng thái nộp:** artifacts chính đã có, bao gồm bonus Nemotron 10/10; chưa sẵn sàng nộp cho đến khi rà sạch toàn bộ artifacts, push và xác nhận LMS. Mốc core >95 chưa đạt.

## 8. Chốt loop cải thiện core · 2026-11-12

- Đọc lại GUIDE/SUBMISSION/CHECKPOINTS trước lượt sửa: giữ nguyên cases, scenarios, fixtures, rubric và giới hạn max steps; core phải có đủ 22 điểm mới hợp lệ. Thay đổi tập trung vào prompt không dùng tool, xử lý mâu thuẫn timeout/operational, căn cứ quote incident khi component rỗng, và caveat giới hạn lịch sử 50 incident.
- Regression/offline verification: core **54/54**, bonus **17/17**, `py_compile` và `git diff --check` đều qua.
- `nemotron_eval_core_final_v5.json` là full run gốc: 20/22 scored, partial mean 96.25; A5 và H4 judge không chấm được. Sau đó A5 được chạy riêng một lần, 98/100 khi Nemotron làm agent và judge. Để giữ judge nhất quán với full run, câu trả lời/trace A5 đã được chấm thêm một lần bằng GPT-OSS: **76/100**. H4 không chạy lại agent; cùng answer/trace từ v5 được chấm lại một lần bằng GPT-OSS: **85/100** sau malformed JSON ban đầu.
- Báo cáo ghép [`nemotron_eval_core_final_reconciled.json`](nemotron_eval_core_final_reconciled.json) có **22/22 case, 94.82/100**. Đây là phép tổng hợp có provenance: 20 case từ full run v5, A5 từ targeted agent rerun rồi chấm GPT-OSS, H4 judge-only retry trên trace cũ. Không phải một lượt full eval duy nhất. Kết quả **chưa đạt >95**; dừng loop tại đây, không lặp case đã có điểm để săn điểm.
- Bonus gần nhất vẫn là artifact full đã ghi ở phần trước; core changes này chưa chạy full bonus lại. Chưa push hoặc nộp LMS.
