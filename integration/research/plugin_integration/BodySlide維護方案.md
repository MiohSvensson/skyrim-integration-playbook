# 新增裝備的 BodySlide 可維護性

本次只讀掃描與建立工具用配方，未執行 BodySlide、未修改來源。

52份裝備的694個專屬ARMA模型路徑，找到415個精確輸出相符的SliderSet；407個已閉合輸入檔案及OSD具名資料集。27份來源插件至少有一項BODYTRI缺件。

有明確CBBE/3BA且輸入閉合的建議有界配方：47個專案，覆蓋94個需morph修復的模型；尚有154個模型沒有可確認的CBBE/3BA重建方案。

兩包目前UI都保存 `- Zeroed Sliders -` 和 `BuildMorphs=true`，也都啟用OBody NG。這只證明目前工具設定；不能反推每份預生成網格的歷史preset。缺TRI的衣服可顯示既有模型，但OBody變形功能不能據此宣告完整。

TuLED工具版本是5.7.0，已按對應tag原始碼確認只支援 `-gbuild`、`-p`、`-t`、`-tri`。新wiki的 `--build`／`--filter` 不套用此版本。

配方位於 `bodyslide_plan/<pack>/SliderSets` 與 `SliderGroups`，每項只改工具顯示名稱以隔離同名專案，其餘XML值原樣保留。ShapeData來源清單在 `bodyslide_maintenance_plan.json`；按pack分開私有ProjectPath，不覆蓋基底CBBE/3BA工具輸入。

原TuLED Config.xml的OutputDataPath指向原包Body Slide Output，不能直接使用。後續若實際重建，須建立Database私有工具/config，使用JSON中明確的 `-t` 輸出到Database，重建後再核對NIF/TRI拓撲、材質、物理及允許輸出清單。

作者來源：[BodySlide 5.7.0 CLI定義](https://github.com/ousnius/BodySlide-and-Outfit-Studio/blob/v5.7.0/src/program/BodySlideApp.h#L198)、[輸入資料夾與具名OSD載入](https://github.com/ousnius/BodySlide-and-Outfit-Studio/blob/v5.7.0/src/components/SliderSet.cpp#L173)。
