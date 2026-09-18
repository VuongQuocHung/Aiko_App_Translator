# Quy Tắc Viết Prompt, Xưng Hô Và Hồ Sơ Nhân Vật Cho Aiko App Translator

> Tài liệu này mô tả **trạng thái mã nguồn đang có trong workspace Aiko App Translator v1.2.2**, rà soát ngày 18/09/2026. Working tree hiện có các thay đổi chưa commit, nên mã nguồn trong máy là căn cứ chính; commit `e103b9cef8abe1d547030957ee700a94b411482d` chỉ là mốc nền.
>
> Phạm vi chính là pipeline desktop/local trong `cores`, `services`, `providers` và `web`. Thư mục `web-client` là ứng dụng độc lập, có cách lưu context và một số prompt cũ khác pipeline desktop; không sao chép prompt giữa hai hệ mà chưa đối chiếu.

## 1. Hiểu đúng cách Aiko tạo một request

Aiko không gửi riêng nội dung người dùng nhập ở ô prompt. Với một chương thông thường, request dịch được ghép từ các lớp sau:

1. `prompt_role`: vai trò dịch của dự án.
2. `style_notes`: quy tắc văn phong toàn truyện.
3. Bộ luật glossary mặc định của ứng dụng.
4. `prompt_task`: nhiệm vụ dịch của dự án.
5. Một số chương dịch liền trước trong `novel.txt`; mặc định là 3 chương.
6. Tối đa 10 cặp xưng hô phù hợp từ `pronouns.json`.
7. Context dự án, gồm glossary, `style_notes`, bản dịch tham khảo và tiêu đề các chương trước.
8. Tiêu đề và nội dung nguồn.
9. Chỉ dẫn bảo toàn mã R19 nếu chế độ R19 đang bật.
10. Contract đầu ra `###TITLE###`, `###CONTENT###`, `###END###`.
11. Snapshot từ `characters.md`, chỉ chứa những hồ sơ được nhận diện là liên quan, nếu provider của công đoạn đó chuyển được tài liệu tham chiếu.

Với Gemini API và OpenAI API, lớp 1–3 được gửi dưới dạng **system instruction**, còn lớp 4–10 nằm trong **user message**. Với provider trình duyệt chỉ có một ô nhập, ứng dụng ghép các phần thành một prompt. Vì vậy, quy tắc phải đúng ở cả hai trường hợp; không dựa vào giả định rằng mọi provider đều có system prompt riêng.

`style_notes` đã được ứng dụng đưa vào system instruction và cũng xuất hiện trong context người dùng. Không chép lại toàn bộ style guide vào `prompt_role` hoặc `prompt_task`, nếu không cùng một chỉ dẫn có thể xuất hiện ba lần.

### Những điểm dễ hiểu nhầm

- Glossary desktop **thường được đưa đầy đủ** vào prompt. Chỉ khi request vượt ngân sách context, ứng dụng mới thử lọc glossary theo văn bản liên quan và giữ các alias liên kết; nếu vẫn quá dài, chương được chia ở ranh giới đoạn/câu thay vì âm thầm cắt nguồn.
- Việc quét chương hiện tại và chương kế tiếp chủ yếu dùng để tìm tên glossary phù hợp khi chọn cặp xưng hô, không có nghĩa glossary luôn được lọc trước mọi request.
- `characters.md` không được gửi toàn bộ. Ứng dụng xếp hạng hồ sơ theo header, tên gốc và biệt danh tìm thấy trong chương/context, rồi lấy tối đa 20 hồ sơ liên quan theo mặc định.
- Pipeline hiện tại chèn bản tóm tắt xưng hô trực tiếp vào prompt; nó **không tự đính kèm** `pronouns_snapshot.yaml` hay `pronouns_snapshot.json` cho một lượt dịch thông thường.
- Khi chương quá dài và bị chia, trạng thái “đã chú giải thuật ngữ lần đầu trong chương” được truyền sang phần tiếp theo.

### Tài liệu nhân vật theo provider

| Provider | Cách nhận snapshot `characters.md` |
|---|---|
| Gemini API | Gửi như một phần tham chiếu riêng trong request |
| OpenAI API | Gửi như file input trong request |
| ChatGPT Web | Chèn nội dung file vào cuối prompt dưới mục `Reference file` |
| Google AI Studio Web | Dán prompt và phần tham chiếu riêng vào giao diện |
| Gemini Web | Ở bước **dịch**, adapter hiện không chèn attachment; ở các bước khác như hiệu đính/review, nội dung tham chiếu được nối vào prompt |

Vì khác biệt cuối cùng, không nên viết một prompt dịch phụ thuộc tuyệt đối vào việc Gemini Web luôn nhìn thấy `characters.md`. Những dữ kiện bắt buộc về tên và cách hiển thị vẫn phải được bảo đảm bằng glossary, xưng hô đã chọn và nguyên tác; nếu cần hồ sơ nhân vật đầy đủ ở bước dịch, dùng provider có chuyển attachment.

## 2. Mỗi loại dữ liệu phải có đúng một nơi chịu trách nhiệm

| Dữ liệu | Nơi lưu | Viết gì ở đó |
|---|---|---|
| Vai trò dịch | `context.json` → `prompt_role` | Danh tính chuyên môn, mục tiêu cấp cao, thứ tự ưu tiên |
| Nhiệm vụ dịch | `context.json` → `prompt_task` | Hành vi phải làm, điều cấm, cách xử lý mâu thuẫn |
| Vai trò hiệu đính | `context.json` → `polish_prompt_role` | Danh tính và phạm vi của biên tập viên |
| Nhiệm vụ hiệu đính | `context.json` → `polish_prompt_task` | Tiêu chí sửa bản nháp, mức được viết lại, điều phải bảo toàn |
| Văn phong | `context.json` → `style_notes` | Giọng kể, nhịp văn, giọng nhân vật, router theo loại cảnh |
| Thuật ngữ | `glossary.txt` | Ánh xạ nguồn–đích và metadata hiển thị |
| Hồ sơ nhân vật | `characters.md` | Danh tính, alias, giới tính, vai trò, quan hệ, trạng thái theo mốc |
| Xưng hô | `pronouns.json` | Người nói, người nghe, tự xưng, cách gọi và timeline |
| Tiêu chí review | Cài đặt `review_bg_criteria` | Điều kiện chấm và loại lỗi cần báo |

Nguyên tắc cốt lõi: **một quy tắc chỉ nên có một nguồn chuẩn**. Nếu giọng của một nhân vật đã nằm trong `style_notes`, nhiệm vụ dịch chỉ cần yêu cầu tuân thủ style prompt; không lặp lại toàn bộ hồ sơ giọng nói.

## 3. Thứ tự ưu tiên khi viết quy tắc

Nên công bố một thứ tự ưu tiên duy nhất trong prompt của dự án:

1. Contract kỹ thuật: marker đầu ra, Markdown ảnh và mã giữ chỗ R19.
2. Quy tắc hiển thị glossary do ứng dụng cung cấp.
3. Sự kiện, chủ thể, POV, kênh nói/suy nghĩ, mức chắc chắn và trình tự nhận thức trong nguyên tác.
4. Quy tắc xưng hô đã khóa và trạng thái nhân vật đúng mốc thời gian.
5. Glossary về tên gọi và thuật ngữ.
6. `style_notes` và giọng nhân vật.
7. Độ mượt, vẻ đẹp câu chữ và sở thích diễn đạt.

Không dùng văn phong để đảo một dữ kiện rõ trong nguồn. Không dùng glossary như nguồn lore. Không dùng hồ sơ của chương sau để làm nhân vật biết trước thông tin ở chương hiện tại.

Nếu nguyên tác mới xác nhận một thay đổi thật sự nhưng `pronouns.json` đang khóa quy tắc cũ, không nên viết prompt bắt AI “tự phá khóa”. Hãy sửa/mở khóa cặp đó trong giao diện rồi dịch lại. `locked` là quyết định của người dùng, không phải gợi ý mềm.

## 4. Cách viết prompt hiệu quả

### 4.1. Tách “bất biến” và “tùy cảnh”

Quy tắc bất biến là những điều luôn phải đúng: không thêm sự kiện, giữ POV, giữ mã R19, đúng glossary. Quy tắc tùy cảnh là lựa chọn có điều kiện: gộp câu khi văn nguồn vụn, giữ câu ngắn khi khoảng ngắt có dụng ý, dùng khẩu ngữ hơn ở cảnh hài.

Mỗi quy tắc tùy cảnh nên có dạng:

```text
Mặc định làm X khi có tín hiệu A; giữ Y khi có tín hiệu B; trong mọi trường hợp không được làm sai C.
```

Ví dụ:

```text
Mặc định tái cấu trúc chuỗi câu ngắn nếu chúng chỉ phản ánh cú pháp nguồn. Giữ câu ngắn khi khoảng ngắt biểu đạt sốc, do dự, nhấn mạnh hoặc nhịp chiến đấu. Dù chọn cách nào, không đổi chủ thể, thứ tự nhận thức hay mức chắc chắn.
```

### 4.2. Viết bằng hành vi có thể kiểm tra

Ưu tiên:

- “Giữ đúng người thực hiện hành động trong từng mệnh đề.”
- “Chỉ thêm từ nối khi quan hệ logic đã có trong nguồn.”
- “Không chuyển lời nói thành độc thoại nội tâm hoặc ngược lại.”
- “Nếu nguồn mơ hồ, giữ độ mơ hồ; không tự chọn một cách giải thích.”

Tránh:

- “Dịch thật hay, có hồn, xuất sắc.”
- “Hãy suy nghĩ thật sâu.”
- “Biến tác phẩm thành kiệt tác.”
- Các khẩu hiệu không tạo ra tiêu chí để kiểm tra đầu ra.

### 4.3. Dùng thứ tự ưu tiên thay cho quy trình giả

Các câu như “đọc ba lượt”, “tự kiểm tra năm lần” không bảo đảm model thực sự lặp. Nên chuyển thành danh sách ưu tiên đầu ra:

```text
Khi lựa chọn cách diễn đạt, ưu tiên theo thứ tự:
1. Đúng dữ kiện và POV.
2. Đủ ý, không thêm hoặc lược.
3. Đúng glossary, xưng hô và định dạng.
4. Câu Việt tự nhiên, đúng giọng cảnh.
5. Nhạc tính và độ gợi.
```

### 4.4. Ví dụ phải dạy đúng một quyết định

Mỗi ví dụ nên ngắn, nêu rõ tín hiệu và khác biệt giữa bản tránh/bản nên dùng. Không đưa hàng chục ví dụ gần giống nhau vào mọi lớp prompt. Ví dụ đặc thù tác phẩm nên nằm trong `style_notes`; ví dụ về thao tác dịch chung mới nằm trong `prompt_task`.

Không dùng ví dụ có tên nhân vật, quan hệ hoặc lore của chương tương lai nếu model có thể bắt chước chúng ở chương sớm.

### 4.5. Độ dài và trùng lặp

Ứng dụng cho phép mỗi trường prompt dài tới 100.000 ký tự, nhưng đó là giới hạn lưu trữ, không phải độ dài khuyến nghị. Prompt càng dài càng cạnh tranh context với nguồn, glossary, bản nháp và hồ sơ nhân vật.

Quy tắc thực dụng:

- `prompt_role`: khoảng 3–8 câu.
- `prompt_task`: một danh sách ưu tiên và các ngoại lệ thực sự cần thiết.
- `polish_prompt_role`: 1–4 câu.
- `polish_prompt_task`: tập trung vào lỗi còn lại sau bước dịch, không sao chép nguyên prompt dịch.
- `style_notes`: có thể dài hơn, nhưng chia theo giọng kể, giọng nhân vật, loại cảnh và motif; xóa phần lặp với prompt nhiệm vụ.

Đừng dựa vào con số trừu tượng như “phóng tác 7/10”. Hãy mô tả quyền được làm cụ thể: được đổi trật tự vế, được gộp câu, được giải nén cảm giác đã có; không được tạo sự kiện, động cơ, hình ảnh hay đánh giá mới.

## 5. Viết `prompt_role`

Vai trò chỉ nên trả lời bốn câu hỏi:

1. AI đang làm nghề gì?
2. Dịch sang ngôn ngữ nào?
3. Mức can thiệp văn phong là gì?
4. Khi đẹp và đúng xung đột, ưu tiên gì?

Mẫu cân bằng:

```text
Bạn là dịch giả kiêm biên tập viên tiểu thuyết sang tiếng Việt. Hãy bảo toàn sự kiện, chủ thể, POV, hàm ý và cường độ cảm xúc của nguyên tác, đồng thời tái cấu trúc cú pháp để văn bản đọc tự nhiên như văn xuôi tiếng Việt. Chất lượng câu chữ không được đánh đổi bằng việc thêm ý, lược ý hoặc làm rõ điều nguyên tác cố ý để mơ hồ. Khi các mục tiêu xung đột, độ chính xác và tính nhất quán của dự án được ưu tiên trước vẻ đẹp câu chữ.
```

Không đưa vào vai trò:

- Nội dung một chương cụ thể.
- Toàn bộ style guide hoặc glossary.
- Danh sách nhân vật và quan hệ.
- Marker đầu ra.
- JSON schema của review.
- Lệnh cập nhật `pronouns.json`.

## 6. Viết `prompt_task`

Nhiệm vụ dịch nên đi từ ràng buộc nghĩa đến lựa chọn văn phong:

```text
Dịch đầy đủ tiêu đề và nội dung sang tiếng Việt.

Ưu tiên theo thứ tự:
1. Giữ đúng sự kiện, chủ thể, quan hệ nhân quả, POV, kênh lời nói/suy nghĩ, mức chắc chắn và trình tự nhận thức.
2. Không thêm hoặc lược thông tin có nghĩa. Nếu nguồn mơ hồ, giữ độ mơ hồ.
3. Tuân thủ glossary, hồ sơ nhân vật, bộ nhớ xưng hô và trạng thái đúng thời điểm của cảnh.
4. Viết lại cú pháp theo thói quen tiếng Việt. Được gộp, tách và đổi trật tự vế khi không làm sai các mục 1–3.
5. Mặc định sửa chuỗi câu vụn mang dấu vết dịch từng câu; giữ câu ngắn khi nhịp ngắt có chức năng nghệ thuật rõ ràng.
6. Giữ đúng giọng kể, giọng nhân vật và mức độ trang trọng theo style prompt. Không tự làm văn bản hoa mỹ, hài hước, thô tục hoặc bi kịch hơn nguồn.
7. Giữ nguyên Markdown ảnh, dấu thoại, ký hiệu đặc biệt và mã giữ chỗ. Không tự thêm Markdown.
8. Tiêu đề viết hoa theo quy tắc tiếng Việt, trừ khi style prompt quy định rõ cách khác.
9. Chỉ trả về bản dịch; không giải thích lựa chọn dịch thuật.
```

Không chèn contract `###TITLE###` vào prompt tùy chỉnh. Aiko tự thêm contract đó sau dữ liệu chương. Nếu prompt tùy chỉnh yêu cầu một định dạng khác, parser có thể từ chối kết quả.

### Phóng tác có kiểm soát

Nếu dự án cần phóng tác, mô tả ba vùng rõ ràng:

- **Được phép:** đổi cấu trúc câu, thay điểm đặt chủ ngữ, dùng thành ngữ tương đương, giải nén cảm giác đã được nguồn chứng minh.
- **Có điều kiện:** thêm từ nối, chủ ngữ ẩn hoặc chi tiết chuyển tiếp tối thiểu khi tiếng Việt cần và nguồn đã suy ra duy nhất.
- **Cấm:** tạo hình ảnh mới, động cơ mới, câu đùa mới, lời giải thích lore, phản ứng cảm xúc hoặc kết luận chắc chắn không có trong nguồn.

## 7. Viết prompt hiệu đính

Hiệu đính nhận cả nguyên tác lẫn bản dịch nháp. Mục tiêu là sửa bản nháp, không tạo một bản dịch khác chỉ vì “có thể hay hơn”.

### Vai trò hiệu đính đề xuất

```text
Bạn là biên tập viên bản dịch tiểu thuyết tiếng Việt. Bạn sửa trực tiếp bản nháp dựa trên nguyên tác, ưu tiên độ chính xác, tính nhất quán và dòng chảy tự nhiên; không viết lại tùy hứng những phần đã đạt.
```

### Nhiệm vụ hiệu đính đề xuất

```text
Đối chiếu nguyên tác với bản dịch hiện có rồi trả về bản hoàn chỉnh.

1. Sửa sai nghĩa, thiếu/thừa ý, hallucination, nhầm chủ thể, sai POV, sai kênh nói/suy nghĩ, sai giới tính và sót ngoại ngữ.
2. Sửa tên, thuật ngữ và cách hiển thị glossary đúng quy tắc hệ thống.
3. Kiểm tra người nói, người nghe và xưng hô theo hồ sơ, timeline và quy tắc đã khóa.
4. Tái cấu trúc đoạn còn mang cú pháp nguồn, câu vụn vô cớ hoặc nối câu quá mức; giữ câu ngắn có dụng ý.
5. Giữ nguyên mọi dữ kiện, Markdown ảnh, dấu thoại, ký hiệu đặc biệt và mã giữ chỗ.
6. Không tăng cảm xúc, không sáng tác thêm, không giải thích thay đổi.
7. Không sửa một câu đã đúng chỉ để thay bằng sở thích diễn đạt khác.
```

Pipeline còn có hai loại sửa khác, không nên trộn vào prompt hiệu đính chính:

- **Sửa glossary:** chỉ sửa các lỗi định dạng thuật ngữ đã được validator liệt kê; code kiểm tra để bảo đảm phần văn xuôi khác không đổi.
- **Hiệu đính lần 2 theo review:** chỉ xuất danh sách thay thế JSON cục bộ cho các issue hợp lệ; không dịch lại cả chương.

Nếu điểm review thấp hơn ngưỡng cấu hình (mặc định 9), Aiko có thể tự chạy hiệu đính lần 2. Bản trước review được lưu dưới dạng `.before-review.bak` và `.before-review.json`.

## 8. Quy tắc xưng hô

### 8.1. Một bản ghi là một chiều giao tiếp

Mỗi record phải có:

- `speaker`: người nói cụ thể.
- `listener`: người nghe cụ thể.
- `speaker_self`: cách người nói tự xưng.
- `speaker_to_listener`: cách người nói gọi người nghe.
- `relationship_status`: trạng thái quan hệ ở mốc đó.
- `emotional_tone`: sắc thái của lượt giao tiếp.
- `chapter_id` và `chapter_number`: mốc thời gian.

Hai chiều A → B và B → A là hai record khác nhau. Không đảo đại từ một cách máy móc.

### 8.2. Dẫn truyện không phải hội thoại

`pronouns.json` được tạo từ các cặp xưng hô rõ ràng trong hội thoại. Không dùng một record hội thoại làm bằng chứng duy nhất để đổi đại từ ngôi ba trong dẫn truyện. Đại từ dẫn truyện còn phụ thuộc POV, giới tính/cơ thể ở thời điểm đó và khoảng cách của người kể.

### 8.3. Chỉ ghi người cụ thể

- Không dùng quốc gia, tổ chức, công chúng, đám đông hoặc nhóm vô danh làm nhân vật.
- Dùng tên thống nhất với glossary và hồ sơ nhân vật.
- Nếu nguồn chỉ có chức danh mà chưa xác định danh tính, không tự gán sang một nhân vật đã biết.
- Chỉ ghi cặp thật sự xuất hiện hoặc được xác nhận; không suy từ quan hệ “có vẻ hợp lý”.

### 8.4. Timeline và khóa

- Chỉ các record có `chapter_number` nhỏ hơn chương hiện tại được đưa vào prompt.
- Ứng dụng ưu tiên cặp liên quan đến tên glossary trong chương; nếu có kết quả liên quan, các cặp không liên quan bị loại.
- Sau đó cặp được xếp theo mức liên quan, trạng thái khóa và độ gần; tối đa 10 cặp.
- Mỗi cặp tự động chỉ giữ 25 record gần nhất.
- `locked` nằm ở **cấp cặp**, không nằm riêng trên một record. Khi một cặp bị khóa, bước cập nhật tự động giữ nguyên toàn bộ cặp đó.
- Khi retry cùng một chương, record tự sinh của chương đó được thay thế thay vì nhân đôi; cặp khóa không bị đụng tới.

Vì khóa có phạm vi cả cặp, chỉ khóa sau khi đã kiểm tra cả hai chiều và timeline. Nếu quan hệ chuẩn bị đổi theo cốt truyện, nên để mở hoặc cập nhật thủ công đúng mốc.

### 8.5. Cấu trúc tham khảo

```json
{
  "An---Bình": {
    "characters": ["An", "Bình"],
    "locked": true,
    "timeline": [
      {
        "chapter_id": "v1_c12_s1",
        "chapter_number": 12,
        "speaker": "An",
        "listener": "Bình",
        "speaker_self": "tôi",
        "speaker_to_listener": "cậu",
        "relationship_status": "Bạn bè thân thiết",
        "emotional_tone": "Thoải mái, có ý trêu chọc",
        "source": "manual"
      }
    ]
  }
}
```

Khóa chuỗi như `An---Bình` là định danh nội bộ. Không tự đổi khóa chỉ để làm đẹp; dùng giao diện chỉnh sửa khi có thể.

## 9. Quy tắc viết `characters.md`

### 9.1. Header quyết định khả năng tìm hồ sơ

Parser chỉ nhận block bắt đầu bằng đúng dạng:

```markdown
## Tên nhân vật
```

Tên header nên là tên đầy đủ, ổn định và trùng với bản dịch chính trong glossary. Không dùng “Nam chính”, “Thủ khoa” hoặc một danh hiệu thay cho tên khi danh tính đã biết.

Snapshot tìm nhân vật qua:

- Header.
- Trường `Tên gốc`.
- Trường `Biệt danh / Danh hiệu`.

Vì vậy hãy đặt tên gốc và alias vào đúng các trường này. Header dạng `Tên dịch / Tên gốc` vẫn có thể được nhận diện, nhưng prompt tạo hồ sơ mặc định yêu cầu một tên đầy đủ theo glossary; dùng một chuẩn xuyên suốt sẽ ít tạo block trùng hơn.

### 9.2. Mẫu hồ sơ nên dùng

```markdown
## Ray Albright

### Thông tin cơ bản
- **Tên gốc**: 레이 올브라이트
- **Biệt danh / Danh hiệu**: Ray / Tân thủ khoa
- **Giới tính**: Nam
- **Tuổi / Độ tuổi ước lượng**: Khoảng 18
- **Chủng tộc / Xuất thân**: Con người
- **Địa vị / Chức vụ**: Học viên
- **Phe / Tổ chức**: Học viện

### Quan hệ và xưng hô
- Với Alice: quan hệ bạn học; cách xưng hô đã xác nhận nằm trong pronouns.json.

### Trạng thái theo thời điểm
- Trước chương 20: chưa biết thân phận thật của Alice.
- Từ chương 20: đã biết nhưng che giấu việc này.

### Ghi chú dịch thuật
- Lời thoại ngắn, khô và có tính châm biếm.
- Không biến lời mỉa mai thành lời xúc phạm thô tục.
```

Template bắt buộc của bộ sinh hồ sơ chỉ có `Thông tin cơ bản` và `Ghi chú dịch thuật`; có thể thêm các mục quan hệ/timeline như trên vì parser giữ nguyên toàn block.

### 9.3. Nhân vật chuyển sinh hoặc biến đổi cơ thể

Ghi riêng:

- Trạng thái trước biến đổi.
- Cơ thể hiện tại.
- Nhận thức của nhân vật về bản thân.
- Cách người khác nhìn nhận.
- Mốc chương của thay đổi.
- Đại từ dẫn truyện theo từng POV và giai đoạn.
- Xưng hô hội thoại theo từng đối tượng nếu đã xác nhận.

Không nén mọi trạng thái vào một dòng `Giới tính: Nam/Nữ`. Hồ sơ được dùng ở nhiều chương, nên thông tin không có mốc rất dễ làm rò rỉ tương lai.

### 9.4. Cập nhật an toàn

- Chỉ ghi dữ kiện được nguồn xác nhận hoặc suy ra gần như duy nhất.
- Dùng `Không xác định` khi chưa đủ căn cứ.
- Không xóa thông tin cũ còn đúng.
- Khi trạng thái thay đổi, thêm mốc thay vì ghi đè lịch sử.
- Giữ nguyên header của nhân vật đã có; trình hợp nhất dùng header làm khóa.
- Tránh hồ sơ quá dài chứa tóm tắt toàn bộ cốt truyện. Snapshot tối đa 20 hồ sơ vẫn tính vào ngân sách context.

## 10. Quy tắc glossary hiện tại

### 10.1. Dạng legacy

```text
Nguyên văn = Bản dịch
```

Dòng legacy vẫn là ánh xạ nguồn → đích, nhưng không có kiểm tra hiển thị chặt như dòng metadata.

### 10.2. Dạng metadata

```text
English = Vietnamese | type=TYPE | first_vi=yes/no | first_en=yes/no | brackets=yes/no | target_only=yes/no
```

Các `type` chuẩn hiện có:

```text
Skill Ability Trait Rank Title Concept System Artifact Organization Faction Place World Species Name Common Alias Unknown
```

`first_vi` và `first_en` loại trừ nhau. Không đặt cả hai thành `yes`.

### 10.3. Bảy chế độ hiển thị

Giả sử `Chain of Heart = Xiềng Xích Trái Tim`:

| Metadata | Lần đầu trong mỗi chương | Các lần sau |
|---|---|---|
| `first_vi=yes`, `brackets=yes` | `[Chain of Heart] (Xiềng Xích Trái Tim)` | `[Chain of Heart]` |
| `first_vi=yes`, `brackets=no` | `Chain of Heart (Xiềng Xích Trái Tim)` | `Chain of Heart` |
| `first_en=yes`, `brackets=yes` | `[Xiềng Xích Trái Tim] (Chain of Heart)` | `[Xiềng Xích Trái Tim]` |
| `first_en=yes`, `brackets=no` | `Xiềng Xích Trái Tim (Chain of Heart)` | `Xiềng Xích Trái Tim` |
| Không first, `brackets=no` | `Chain of Heart` | `Chain of Heart` |
| Không first, `brackets=yes` | `[Chain of Heart]` | `[Chain of Heart]` |
| `type=Common` hoặc `target_only=yes` | `Xiềng Xích Trái Tim` | `Xiềng Xích Trái Tim` |

`type=Common` và `target_only=yes` là ngoại lệ ưu tiên cao nhất: chỉ xuất bản dịch tiếng Việt, không giữ tiếng Anh, không chú giải song ngữ và không thêm ngoặc vuông. Chế độ này ghi đè `first_vi`, `first_en` và `brackets`.

### 10.4. Quy tắc dữ liệu

- Vế trái phải là cụm thật sự xuất hiện trong nguồn và không chứa `=`.
- Không dùng `|`, xuống dòng hoặc khóa metadata có `=` trong giá trị.
- Một nguyên văn chỉ có một mục chính; nếu trùng, parser lấy dòng hợp lệ sau cùng.
- Sửa mục cũ thay vì giữ hai cách dịch mâu thuẫn.
- Dùng `canonical=...` hoặc alias có chủ đích; bộ lọc giữ các alias liên kết theo đích/canonical.
- Ưu tiên cụm dài hơn khi một thuật ngữ chứa thuật ngữ khác.
- Với từ `Common`, chỉ áp dụng khi đúng ngữ cảnh; không ép một nghĩa thuật ngữ lên từ phổ thông không liên quan.
- Lần xuất hiện đầu được reset ở mỗi chương, không phải mỗi request/chunk.
- Tiêu đề chương, prompt, glossary, ví dụ, hồ sơ và chương tham khảo không được tính là lần xuất hiện trong truyện.

Validator chỉ phát hiện và yêu cầu sửa; nó không tự thay từ bằng thao tác chuỗi. Bản sửa glossary chỉ được chấp nhận nếu hết lỗi và phần văn xuôi ngoài thuật ngữ giữ nguyên.

## 11. Viết `style_notes`

`style_notes` là nơi chứa bản sắc của tác phẩm, không phải nơi chứa mọi quy tắc kỹ thuật.

Nên chia thành:

1. Giọng kể và POV.
2. Nhịp câu mặc định.
3. Dấu thoại và quy ước trình bày riêng của truyện.
4. Router theo loại cảnh: chiến đấu, đời thường, hài, nội tâm, kinh dị, nghi lễ...
5. Giọng của các nhân vật chính.
6. Motif và trường từ vựng cần giữ nhất quán.
7. Ngoại lệ có tín hiệu nhận biết rõ.

Ví dụ ngắn:

```text
## Giọng kể
- Ngôi thứ nhất, hiện đại, tỉnh và tiết chế.
- Không biến nhận xét khô thành độc thoại trữ tình.

## Router cảnh
- Chiến đấu: động từ cụ thể, quan hệ không gian rõ, câu ngắn hơn nhưng không chặt vụn từng hành động.
- Đời thường: ưu tiên khẩu ngữ tự nhiên và nhịp đáp; không thêm tiếng lóng ngoài tính cách.
- Nội tâm: cho phép câu dài hơn để giữ dòng giằng co, nhưng bảo toàn thứ tự nhân vật nhận ra thông tin.

## Giọng Ray
- Ít lời, khô, mỉa nhẹ; tránh văn cổ và tránh chửi tục nếu nguồn không có.
```

Không đưa vào `style_notes`:

- Toàn bộ glossary.
- Tiểu sử đầy đủ của mọi nhân vật.
- Timeline xưng hô của từng cặp.
- Contract đầu ra hoặc JSON schema.
- Quy tắc chỉ đúng với một cảnh duy nhất mà không có điều kiện nhận diện.

## 12. Contract kỹ thuật không được ghi đè

### Dịch và hiệu đính

```text
###TITLE###
<tiêu đề>

###CONTENT###
<nội dung>

###END###
```

### Batch

Batch có thêm `###START###`, `###SECTION n###` và một cặp `TITLE/CONTENT` cho mỗi chương. Không yêu cầu AI đổi tên marker hoặc chèn giải thích ngoài marker.

### Hồ sơ nhân vật

Kết quả phải nằm trong một code block `markdown`, bắt đầu bằng `###START###`, kết thúc bằng `###END###`, và có ít nhất một header `## Tên nhân vật`.

### Glossary generation

Mỗi dòng là `Nguyên văn = Bản dịch`, nằm giữa `###START###` và `###END###`, không thêm Markdown hay lời giải thích.

### R19

Mọi token bắt đầu bằng `__20AGE_` phải được sao chép nguyên vẹn, đúng thứ tự và đủ số lần. Không dịch, tách, đổi tên, thêm khoảng trắng hoặc escape token. Khi bật R19, ứng dụng còn bọc prompt bằng prefix cấu hình; prompt tùy chỉnh không được tự đóng/mở cặp dấu bọc đó.

## 13. Pipeline sau dịch và ảnh hưởng tới cách viết prompt

Luồng mặc định hiện tại:

```text
Dịch → Hiệu đính → Sửa sót ngoại ngữ → Kiểm tra/sửa glossary
     → Cập nhật pronouns.json → Lưu → Review → Có thể hiệu đính lần 2
```

Hệ quả:

- Prompt dịch không cần yêu cầu tự review JSON.
- Prompt dịch/hiệu đính không cần yêu cầu cập nhật `pronouns.json`; bước trích xuất chạy sau bản cuối của hậu xử lý.
- Prompt hiệu đính phải giữ nguồn và bản nháp thẳng hàng về nội dung vì chương dài có thể được chia thành các segment tương ứng.
- Review chỉ nên báo lỗi có dẫn chứng; khác biệt diễn đạt thuần túy không phải lỗi.
- Hiệu đính lần 2 chỉ sửa issue review hợp lệ bằng thay thế cục bộ. Không dùng prompt review như một style guide thứ hai.
- Khi công đoạn polish tắt, validator vẫn có thể báo lỗi glossary nhưng không gọi model để sửa.

## 14. Checklist trước khi lưu prompt

### Cấu trúc

- [ ] `prompt_role` ngắn và chỉ chứa mục tiêu cấp cao.
- [ ] `prompt_task` mô tả hành vi cụ thể, có thứ tự ưu tiên.
- [ ] Prompt dịch và prompt hiệu đính không sao chép nguyên xi nhau.
- [ ] Quy tắc văn phong chi tiết nằm trong `style_notes`.
- [ ] Không lặp glossary, hồ sơ nhân vật hoặc timeline xưng hô trong prompt tùy chỉnh.

### Tính nhất quán

- [ ] Chỉ có một quy tắc viết hoa tiêu đề.
- [ ] Chỉ có một định nghĩa về mức phóng tác.
- [ ] Quy tắc gộp câu có ngoại lệ cho khoảng ngắt mang dụng ý.
- [ ] Không có chỉ dẫn vừa “giữ nguyên tuyệt đối cấu trúc” vừa “viết lại tự do”.
- [ ] Không có ví dụ làm lộ lore tương lai.

### Dữ liệu dự án

- [ ] Glossary dùng đúng metadata và chế độ hiển thị mong muốn.
- [ ] Tên nhân vật khớp giữa glossary, header hồ sơ và pronouns.
- [ ] Hồ sơ biến đổi trạng thái có mốc chương.
- [ ] Mỗi cặp xưng hô được kiểm tra riêng theo hai chiều.
- [ ] Chỉ khóa cặp sau khi xác nhận toàn bộ timeline cần giữ.

### Đầu ra

- [ ] Không ghi đè marker do ứng dụng tự thêm.
- [ ] Markdown ảnh và dấu thoại được bảo toàn.
- [ ] Token R19 không bị biến đổi.
- [ ] Không yêu cầu giải thích ngoài bản dịch.

## 15. Những lỗi cần tránh riêng với Aiko

- Không viết `pronouns_snapshot.yaml` vào prompt như thể file đó luôn được đính kèm.
- Không khẳng định glossary luôn được lọc theo chương hiện tại và chương sau; đó không phải luồng desktop hiện tại.
- Không coi `locked` là khóa một record; nó khóa cả cặp trong bước cập nhật tự động.
- Không dùng `characters.md` như kho tóm tắt truyện không giới hạn; snapshot được đính kèm và tiêu tốn context.
- Không dùng `type` để suy ra cách hiển thị ngoại trừ `Common`; với các type khác, `target_only`, `first_vi`, `first_en` và `brackets` mới quyết định hình thức.
- Không yêu cầu model tự đổi chính tả canonical để tránh lặp từ; glossary formatting ưu tiên hơn biến thể văn phong.
- Không chèn lại `GLOSSARY FORMATTING RULES`; ứng dụng tự thêm bộ luật từ `defaults/glossary_rules.txt`.
- Không yêu cầu “sửa mọi thứ” ở bước hiệu đính lần 2; code chỉ chấp nhận các edit gắn với issue review.
- Không sao chép prompt từ `web-client` sang desktop mà không sửa các giả định YAML, Hàn–Việt và `pronouns_snapshot.yaml` còn sót trong hệ độc lập đó.
- Không dùng prompt cực dài chỉ vì giới hạn lưu trữ cho phép; prompt, nguồn, glossary, bản nháp và attachment dùng chung ngân sách context.

## 16. Nguồn đối chiếu trong repository

- Ghép system/user prompt, preset, marker và R19: [`cores/translation/prompts.py`](cores/translation/prompts.py)
- Chia chương và kiểm soát ngân sách: [`cores/translation/stage.py`](cores/translation/stage.py), [`cores/stages/budget.py`](cores/stages/budget.py)
- Thứ tự pipeline và review lại: [`cores/translation/runner.py`](cores/translation/runner.py), [`cores/postprocess/pipeline.py`](cores/postprocess/pipeline.py)
- Parse, lọc và metadata glossary: [`cores/context/glossary.py`](cores/context/glossary.py)
- Luật hiển thị glossary: [`defaults/glossary_rules.txt`](defaults/glossary_rules.txt)
- Validator và trạng thái first mention: [`cores/context/validation.py`](cores/context/validation.py)
- Context đưa vào prompt: [`cores/context/storage.py`](cores/context/storage.py)
- Chọn và định dạng xưng hô: [`cores/pronouns/context.py`](cores/pronouns/context.py), [`cores/pronouns/extraction.py`](cores/pronouns/extraction.py)
- Sinh, parse và hợp nhất hồ sơ: [`cores/characters/prompt.py`](cores/characters/prompt.py), [`cores/characters/parser.py`](cores/characters/parser.py)
- Snapshot nhân vật liên quan: [`cores/postprocess/snapshots.py`](cores/postprocess/snapshots.py), [`cores/stages/references.py`](cores/stages/references.py)
- Prompt hiệu đính, review và sửa cục bộ: [`cores/postprocess/polish.py`](cores/postprocess/polish.py), [`cores/postprocess/review.py`](cores/postprocess/review.py), [`cores/postprocess/review_correction.py`](cores/postprocess/review_correction.py)
- Lưu và kiểm tra các trường prompt: [`services/context/service.py`](services/context/service.py)
- Hệ prompt độc lập của web client: [`web-client/src/services/gemini.ts`](web-client/src/services/gemini.ts)

---

Tóm lại: prompt tốt cho Aiko không phải prompt chứa mọi thứ. Nó là một bộ quy tắc ngắn, phân tầng và không trùng lặp, biết rõ phần nào ứng dụng đã tự cung cấp. Hãy để prompt quyết định **cách xử lý**, glossary quyết định **thuật ngữ hiển thị ra sao**, hồ sơ quyết định **nhân vật là ai**, timeline quyết định **ai xưng với ai thế nào**, và code quyết định **định dạng đầu ra**.
