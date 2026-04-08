import pypandoc
import os

md_file = r'c:\Users\kevin\Desktop\data_platform\发明专利-基于多模态大语言模型的风力发电机组智能运维系统及方法.md'
docx_file = r'c:\Users\kevin\Desktop\data_platform\发明专利-基于多模态大语言模型的风力发电机组智能运维系统及方法.docx'

try:
    pypandoc.download_pandoc()
    print("Pandoc下载成功")
except Exception as e:
    print(f"Pandoc下载失败: {e}")

try:
    pypandoc.convert_file(md_file, 'docx', outputfile=docx_file, extra_args=['--toc', '--toc-depth=3'])
    print(f"转换成功！文件已保存到: {docx_file}")
except Exception as e:
    print(f"转换失败: {e}")
