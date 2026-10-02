"""镜像解释过程中可能抛出的异常。"""


class ImageRejectedError(Exception):
    """镜像违反层语义（如祖先为非目录、硬链接目标非法），应被拒绝。"""
