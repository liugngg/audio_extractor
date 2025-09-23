# 音频批量提取工具 audio_extractor

## 1.主要功能：
1. 在给定文件夹中，搜寻所有的视频文件，批量提取其中的音频并保存（直接拷贝音频流，不进行格式转换）。
2. 主要采用ffmpeg命令提取：
``` cmd
ffmpeg -i /input/my_video.mkv -map 0:a:0 -c copy /output/extracted_audio.mka
```
命令解释：
- -i /input/my_video.mkv：指定输入文件。
- -map 0:a:0：选择第一个音轨（索引0）。如果要提取第二条音轨，改为 -map 0:a:1。
- -c copy：最关键参数。表示直接复制音频流，不重新编码，实现无损提取。
- /output/extracted_audio.mka：输出文件和路径。容器扩展名很重要，建议根据音频格式选择：
AAC音频（来自MP4）：.m4a
AC3音频：.ac3
DTS音频：.dts
通用容器：.mka (Matroska Audio) 通常是不错的选择。


## 2. 打包命令
- 生成单文件格式
  `pyinstaller -F -w audio_extractor.py --clean -n '音频批量提取工具'
- 生成文件夹的形式
  `pyinstaller -D -w audio_extractor.py --clean -n '音频批量提取工具'

## 3. 作者
- [liugngg (GitHub地址)](https://github.com/liugngg)
