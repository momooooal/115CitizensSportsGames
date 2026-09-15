# 高雄上場｜115 全民運選手追蹤

給高雄選手、家人與加油團使用的賽程網站。查姓名就能查看已對應的比賽日期、時間、對手、晉級狀態與官方最終名次；每筆資料附官方依據。

網站採繁體中文，支援手機與桌面排版，不需要登入。可按日期、競賽種類、姓名與狀態篩選，也能匯出 CSV。點選手姓名可查看個人場次；「決賽與名次」集中顯示晉級與最終成績。

## 這次更新：已排日期照常顯示

尚未公布個別選手出場名單或實際時間的賽程，現在也會列在「比賽日程」，附高雄相關組別的報名選手名單，標示「個別出賽待確認」。搜尋姓名、指定日期、選手個人頁與 CSV 匯出都能查到。

- 已知項目時間：保留原本的表定時間，另註「高雄選手實際出賽時間待公布／確認」。
- 只有競賽日期範圍：期間內的日期保留日程參考，標示「競賽期間」；名單不代表每位選手當天都要出賽。
- 已有部分選手場次：其他報名選手的待確認資訊仍會保留。
- 官方補上本輪名單：下一次同步會改以具名場次顯示，不重複列出同一場待確認項目；同日預賽與決賽分別處理。

若已把上一版放到 GitHub，將壓縮檔內同名檔案覆蓋回原位置即可，網址與 Pages 設定沿用。更新完整 `site`、`scripts`、`tests` 資料夾；這次預覽仍使用下方標示的官方資料快照，不把介面修改時間當作新的成績取得時間。

## 先在電腦看網站

解壓縮後，用瀏覽器開啟 `site/index.html`。隨附的資料可以直接查詢；下載版會顯示資料時間，啟用 GitHub Pages 流程後才會定期同步。

也可以開啟另外提供的「高雄上場-預覽.html」，它已包含全部網頁檔案及這次的資料快照。

## 用 GitHub 網頁介面上線

1. 登入 GitHub，建立新的 **Public** repository，名稱可用 `kaohsiung-sport115`。可勾選建立 README，方便進入上傳畫面。
2. 解壓縮網站 ZIP。進入 repository，選 **Add file → Upload files**，上傳解壓縮後的內容，保留資料夾結構。上傳的是 `site`、`scripts`、`tests`、`.github`、`README.md`、`requirements.txt` 等內容，不是 ZIP 本身。提交到 `main`。
3. 確認根目錄能看到 `site` 與 `.github/workflows/update-and-deploy.yml`。若電腦未顯示 `.github`，先開啟檔案管理員的「顯示隱藏檔案」；也可在 GitHub 選 **Add file → Create new file**，檔名填入 `.github/workflows/update-and-deploy.yml`，貼上壓縮檔內同名檔案的完整內容。
4. 進入 **Settings → Pages**，在 **Build and deployment → Source** 選 **GitHub Actions**。
5. 到 **Actions**，選「**更新高雄賽事並發布網站**」，按 **Run workflow**，使用 `main` 分支。第一次不需勾選完整更新；若要立刻重新讀取所有名單和 PDF，可勾選。
6. 等待 `build` 和 `deploy` 變成綠色。網站網址會顯示在這次流程的 `deploy` 區塊，或 **Settings → Pages** 的 **Visit site**。以 GitHub 顯示的實際網址為準。

如果第一次上傳時流程在 Pages 尚未設定前就啟動而失敗，完成第 4 步後，再執行第 5 步即可。

若流程在「保存本次資料」顯示寫入權限不足，請到 **Settings → Actions → General → Workflow permissions** 選 **Read and write permissions** 並儲存，再重新執行。若 repository 有分支保護規則，也需要允許此流程更新資料，或改用獨立資料分支。

發布方式依 [GitHub Pages 官方工作流程文件](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) 設定。這份交付檔案尚未連到你的 GitHub 帳號，也尚未在你的帳號下公開發布。

## 更新方式

| 資料 | 更新方式 |
| --- | --- |
| 比賽日程、最終成績、前後一天內的逐場報告與出場名單 | 2026 年 9–10 月，每 10 分鐘提出一次 GitHub Actions 更新 |
| 全市名單、項目目錄、其他日期的逐場報告與名單、官方附件 | 每日檢查一次；可手動選完整更新 |
| 已開啟的網頁 | 每分鐘檢查網站是否有新的資料版本 |
| 官網暫時故障、附件失敗 | 保留上次成功的整份資料，顯示同步失敗提醒 |
| 2026 年 11 月以後 | 保留網站與資料；可在 Actions 手動更新，定時擷取停止 |

「檢查更新」按鈕讀取最近已發布的資料，不會在你的瀏覽器直接爬官網。官網公告、GitHub 排程、資料整理與發布都可能造成延遲，因此不是逐秒直播。GitHub 的定時工作可能延後；公開 repository 長期沒有活動也可能停用排程。詳見 [GitHub schedule 說明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

想立即確認最新結果，可點每一場的「官方依據」。網站會顯示資料取得時間；超過 45 分鐘會提醒可能過期。

## 目前資料範圍與判讀

隨附快照的官方資料取得日期為 **2026-09-14**。之後的數量會隨官方更新而改變。

| 範圍 | 這次整理 |
| --- | --- |
| 競賽種類 | 全部 32 種的日期期間、場地及官方資料入口 |
| 高雄報名資料 | 798 筆選手報名人次，排除教練與職員 |
| 姓名查詢 | 767 筆以「種類＋姓名」整理的選手登錄；同名跨種類分列 |
| 已整理場次 | 143 筆，包含明確標示的晉級待確認場次；另列已排日期的個別出賽待確認資訊 |
| 官方詳細賽程附件 | 48 份、228 頁；47 份可站內搜尋文字，1 份需開啟影像 PDF |
| 已公告最終成績 | 3 筆；團體項目不會把每位隊員重複算成一面獎牌 |

目前能自動對應姓名與時間的資料來自已發布的 HTML 成績／出場表，以及部分已核對格式的官方 PDF，包括滑輪溜冰、五人制足球、木球、太極拳、慢速壘球、沙灘手球、巧固球、躲避球與合球。其他已排日期同樣列入比賽日程，附高雄報名名單、待確認標示與官方附件。**143 筆不代表全賽會的所有個人場次都已完成轉換；競賽期間參考筆數也不是確定出賽場次數。**

網站保留以下區分：

- **表定時間**：已能對應這場比賽的時間，仍可能受現場調度影響。
- **項目開始**：整個項目的開始時間。個人出場可能依賽序延後；有官方出場順序時一併顯示。
- **種類比賽期間**：整個競賽種類的日期範圍，不代表每位選手每天出賽。
- **個別出賽待確認**：已有競賽日期或項目賽程，但個人日期、時間或出場名單尚待公布／核對；列出的姓名是相關報名名單。
- **晉級待確認**：賽程已預排決賽，但官方還沒有確認這位選手晉級。顯示的是項目報名名單。
- **已確認晉級決賽**：依官方晉級標記、本輪出場名單，或官方對戰表搭配已公告勝隊判定；推導時會標示依據。
- **本輪名次／最終名次**：預賽第一名不會被當成冠軍。最終名次採官方決賽成績表；團體項目的第三名以後不等於參加過冠軍戰。
- **待官方更新**：預定時間已到但尚未取得成績。不推測正在比賽、落敗或淘汰。

隊伍報名名單不等於當場實際上場的隊員。本站沒有公開的個人識別碼可區分同種類中的完全同名者，姓名有疑義時請回官方名單核對。附件文字搜尋保留內容，合併儲存格和對戰線則以原始 PDF 排版為準。

## 官方資料來源

- [115 全民運官方首頁](https://sport115.tycg.gov.tw/Module/Home/Index.php)
- [高雄市報名名單](https://sport115.tycg.gov.tw/Module/SignupStats/Sta_Unit_Peoples_List.php?UID=014)
- [高雄市官方決賽成績](https://sport115.tycg.gov.tw/Module/Score/Final_Query.php?UID=014)
- [各種類競賽日期與場地](https://sport115.tycg.gov.tw/Module/Pages/Index.php?ID=425)
- [即時成績入口](https://sport115.tycg.gov.tw/Module/Score/Instant.php)
- [全部競賽種類及附件目錄](https://sport115.tycg.gov.tw/Module/SportItem/ALL_Index.php)

網站聚焦高雄選手追蹤所需的競賽資料；相關競賽規程、秩序冊與場地資訊保留官方連結。官方新聞、觀光與一般行政網頁可由官網首頁查看。

## 給維護者

前端是 HTML、CSS、JavaScript，不需 npm 安裝或打包，GitHub Pages 發布目錄是 `site`。後端更新使用 Python 3.12；瀏覽器只讀取同站資料，沒有公開的帳號金鑰或跨站代理。

| 檔案 | 用途 |
| --- | --- |
| `site/index.html`、`styles.css`、`app.js` | 網頁與查詢介面 |
| `site/data/snapshot.json`、`snapshot.js` | 可查詢的姓名、場次、最終成績與來源 |
| `site/data/documents.json`、`documents.js` | 官方附件文字與表格 |
| `site/data/sync-status.json` | 最近同步是否成功 |
| `scripts/update.py` | 完整更新入口，失敗保留前次資料 |
| `scripts/sync_data.py` | 官方 HTML、名單、成績、對戰表整合 |
| `scripts/sync_documents.py`、`pdf_events.py` | 附件擷取與已驗證版型的場次對應 |
| `.github/workflows/update-and-deploy.yml` | 定時更新與 GitHub Pages 發布 |
| `tests/` | 時間、成績判讀、資料完整性與失敗保留檢查 |

本機更新：

```bash
python -m pip install -r requirements.txt
python scripts/update.py --full
```

驗證：

```bash
python -m unittest discover -s tests -p 'test_*.py'
node --test tests/app.test.cjs
node --check site/app.js
```

資料取得最多同時使用 3 個連線；全市名單讀取全部分頁並核對筆數，下載失敗會重試。GitHub Actions 保存來源快取，避免每次重讀全部歷史報告。整個 HTML 與 PDF 更新通過檢查後才替換公開資料。不要把報名名單直接配給所有決賽，也不要只靠預賽排名推測晉級。

官網可能新增賽種報告格式或變更 PDF 排版。遇到無法辨識的報告，檢查 `meta.unrecognized_reports` 與官方原頁，擴充對應解析器，再加入能驗證實際錯誤的測試。原始 HTML 快取只放在 `.cache` 與 Actions 快取，不發布於網站。

這次交付已做資料與程式邏輯驗證、官方 PDF 表格抽查；GitHub 線上部署仍需依前述步驟在你的帳號啟用。
