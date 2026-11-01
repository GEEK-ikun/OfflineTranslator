# 模型目录

**仓库里不含模型权重**——两个模型加起来 164 MB，不适合放进 Git。

程序运行时会在这里找模型：

```
models/packages/translate-en_zh-1_9/
models/packages/translate-zh_en-1_9/
```

## 怎么拿到

### 方式一：从 Argos 官方下载（推荐）

打开 <https://www.argosopentech.com/>，或直接下载这两个文件：

- `translate-en_zh-1_9.argosmodel`（约 70 MB）
- `translate-zh_en-1_9.argosmodel`（约 72 MB）

`.argosmodel` 就是一个 zip 包。解压后把里面的 `translate-en_zh-1_9` 和
`translate-zh_en-1_9` 两个文件夹放进 `models/packages/`。

### 方式二：用 Argos 自带的包管理器

```powershell
pip install argostranslate
argospm install translate-en_zh
argospm install translate-zh_en
```

模型会被装到 Argos 自己的目录（`%USERPROFILE%\.local\share\argos-translate\packages`）。
把这个目录里的两个包复制进本项目的 `models/packages/` 即可。

### 方式三：用环境变量指向别处

不想复制模型，可以让程序去别的地方找：

```powershell
$env:OFFLINETRANSLATOR_MODELS = "D:\models"
python src\main.py
```

程序会在 `D:\models\packages\` 下找那两个包。

## 最终结构应该长这样

```
models/
└── packages/
    ├── translate-en_zh-1_9/
    │   ├── metadata.json
    │   ├── sentencepiece.model
    │   ├── shared_vocabulary.json
    │   ├── model/
    │   │   ├── model.bin        ← 约 79 MB
    │   │   └── config.json
    │   └── stanza/...
    └── translate-zh_en-1_9/
        └── （同上）
```

## 许可

这两个模型由 [Argos Open Tech](https://www.argosopentech.com/) 提供，采用
**CC-BY-4.0**，训练数据来自 OPUS。再分发时必须保留署名，详见
[assets/LICENSE-THIRD-PARTY.md](../assets/LICENSE-THIRD-PARTY.md)。

注意：**CC-BY-4.0 不适用本项目的 MIT 许可**，两者是分开的。
