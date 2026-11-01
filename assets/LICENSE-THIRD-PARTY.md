# 第三方组件与模型许可（Third-Party Notices）

本软件《离线英汉互译（OfflineTranslator）》使用了以下开源组件与公开模型。
本文件保留它们的署名与许可证信息，符合各自许可要求。

## 1. 程序组件

| 组件 | 用途 | 许可证 | 主页 |
| --- | --- | --- | --- |
| Argos Translate | 离线翻译引擎（模型管理与翻译调度） | MIT | https://github.com/argosopentech/argos-translate |
| CTranslate2 | 神经机器翻译推理后端 | MIT | https://github.com/OpenNMT/CTranslate2 |
| SentencePiece | 子词切分 | Apache-2.0 | https://github.com/google/sentencepiece |
| Stanza | 可选的分句/分词依赖（Argos 间接依赖） | Apache-2.0 | https://github.com/stanfordnlp/stanza |
| PyInstaller | 打包工具（仅构建期使用，不随程序分发） | GPL-2.0 with Bootloader Exception | https://pyinstaller.org |

第三方组件各自的许可证全文，请访问上表主页查看。

## 2. 翻译模型（随软件分发的关键数据）

| 模型 | 语言对 | 来源 | 许可证 |
| --- | --- | --- | --- |
| translate-en_zh-1_9 | 英语 → 中文 | Argos Open Tech 模型库 https://www.argosopentech.com/ | CC-BY-4.0 |
| translate-zh_en-1_9 | 中文 → 英语 | Argos Open Tech 模型库 https://www.argosopentech.com/ | CC-BY-4.0 |

- 模型训练数据来自 OPUS 公开平行语料项目（https://opus.nlpl.eu/）。
- 模型随本软件一起分发，安装后即可离线使用；程序运行期不会联网下载模型。
- 模型权重可用于非商业与商业场景，但需保留署名（本文件即为署名文件之一）。

## 3. 界面图标

本软件图标由本项目自行提供（assets/icon.ico），不含第三方版权素材。

## 4. 声明

本软件为免费、离线、无广告工具软件，不收集、不上传用户数据。
如果上述任一组件或模型的作者认为本分发方式不妥，请联系本项目，我们将立即调整。
