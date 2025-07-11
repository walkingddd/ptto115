import os
import time
from p115client.client import P115Client
from p115client.tool.upload import multipart_upload_init

# ======================== 环境变量配置（优先读取，无则用默认值） ========================
# 115客户端配置（环境变量名建议大写，便于区分）
# 环境变量说明：
#   - ENV_115_COOKIES：115登录cookies字符串
#   - ENV_115_UPLOAD_PID：上传目标目录ID（整数）
#   - ENV_DELETE_INTERVAL_HOURS：定时删除间隔（小时，整数，0则关闭）

try:
    # 读取115 cookies（字符串，默认值为占位符，实际使用需通过环境变量设置）
    COOKIES = os.getenv("ENV_115_COOKIES", "ck1111")

    # 读取上传目标目录ID（整数，默认0）
    UPLOAD_TARGET_PID = int(os.getenv("ENV_115_UPLOAD_PID", "0"))

except ValueError as e:
    # 环境变量值格式错误（如非整数），使用默认值并提示
    print(f"环境变量格式错误：{e}，将使用默认配置")
    COOKIES = "ck1111"
    UPLOAD_TARGET_PID = 0

# ======================== 其他固定配置 ========================
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "upload")  # 待上传目录
SLEEP_AFTER_FILE = 10  # 单个文件处理后休眠（秒）
SLEEP_AFTER_ROUND = 60  # 一轮遍历后休眠（秒）


# ======================== 工具函数 ========================
def check_file_size_stability(file_path, check_interval=30, max_attempts=1000):
    """检查文件大小稳定性，防止文件不完整"""
    for attempt in range(max_attempts):
        size1 = os.path.getsize(file_path)
        time.sleep(check_interval)
        size2 = os.path.getsize(file_path)
        if size1 == size2:
            print(f"[信息] 文件大小稳定：{file_path}")
            return True
        print(f"[警告] 文件大小不稳定，第 {attempt + 1} 次检查：{file_path}")
    print(f"[错误] 文件大小不稳定，放弃上传：{file_path}")
    return False


def init_115_client():
    """初始化115客户端（cookies认证）"""
    try:
        client = P115Client(COOKIES)
        print("[信息] 客户端初始化成功（cookies有效）")
        return client
    except Exception as e:
        print(f"[错误] 客户端初始化失败（检查cookies是否有效）：{e}")
        raise


# ======================== 核心逻辑 ========================
def main():
    cache = {}  # 内存缓存：{文件绝对路径: SHA1}
    client = init_115_client()
    last_delete_time = time.time()

    while True:
        print("[信息] 开始遍历待上传目录...")
        # 遍历upload目录文件
        for root, _, files in os.walk(UPLOAD_DIR):
            for filename in files:
                file_path = os.path.join(root, filename)
                file_key = file_path

                print(f"[信息] 正在检查文件 {file_path} 的大小稳定性...")
                # 检查文件大小稳定性
                if not check_file_size_stability(file_path):
                    continue

                # 获取文件大小
                try:
                    filesize = os.path.getsize(file_path)
                    print(f"[信息] 获取到文件 {file_path} 的大小为 {filesize} 字节")
                except FileNotFoundError:
                    print(f"[信息] 文件已删除：{file_path}")
                    if file_key in cache:
                        del cache[file_key]
                    continue

                # 检查缓存中是否有哈希值
                cached_sha1 = cache.get(file_key)
                if cached_sha1:
                    print(f"[信息] 使用缓存的SHA1值：{file_path} → {cached_sha1}")
                else:
                    print(f"[信息] 缓存中无SHA1值，将通过上传接口自动计算")

                # 调用秒传接口（使用环境变量配置的PID）
                try:
                    print(f"[信息] 开始上传文件：{file_path}")
                    upload_result = multipart_upload_init(
                        client=client,
                        path=file_path,
                        filename=filename,
                        filesize=filesize,
                        filesha1=cached_sha1 or '',  # 使用缓存的哈希值或留空让接口自动计算
                        pid=UPLOAD_TARGET_PID
                    )

                    # 处理秒传结果
                    if "status" in upload_result:
                        print(f"[成功] 秒传成功：{file_path}（目标目录ID：{UPLOAD_TARGET_PID}）")
                        os.remove(file_path)
                        print(f"[信息] 已删除本地文件：{file_path}")
                        if file_key in cache:
                            del cache[file_key]
                    else:
                        print(f"[失败] 秒传未成功：{file_path}，从上传配置信息里获取哈希值并缓存")
                        # 从上传配置信息里获取哈希值
                        filesha1 = upload_result.get('filesha1', '')
                        if filesha1:
                            cache[file_key] = filesha1
                            print(f"[信息] 已缓存文件哈希值：{file_path} → {filesha1}")

                except Exception as e:
                    print(f"[错误] 上传失败：{file_path} → {e}")

                #print(f"[信息] 单个文件处理完成，休眠 {SLEEP_AFTER_FILE} 秒...")
                #time.sleep(SLEEP_AFTER_FILE)

        #print(f"[信息] 一轮遍历完成，休眠 {SLEEP_AFTER_ROUND} 秒...")
        #time.sleep(SLEEP_AFTER_ROUND)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[信息] 用户终止程序")
    except Exception as e:
        print(f"[错误] 程序异常：{e}")