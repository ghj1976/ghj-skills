

## 常见agent的skill目录



| Agent        | 全局skill目录                                 | 项目skill目录                            |
| ------------ | ----------------------------------------- | ------------------------------------ |
| OpenCode     | `~/.config/opencode/skills/<skill-name>/` | `.opencode/skills/<skill-name>/`     |
| Hermes Agent | ~/.hermes/skills/                         | 项目根目录下的 `skills/`                    |
| Codex        | `~/.agents/skills/` 或 `~/.codex/skills/`  | `.agents/skills/` 或 `.codex/skills/` |





## 软链接


#### mac和linux下 `ln` 命令


``` bash
ln -s /path/to/original_dir link_to_dir
```



#### win下cmd中的 `mklink` 命令


`mklink` 是嵌入在 `cmd.exe` 里的“内部命令”，并不是一个独立的可执行程序，所以没法在 PowerShell 里直接运行


**步骤**

1. 右键点击开始菜单，选择 **“终端(管理员)”** 或 **“命令提示符(管理员)”**，以管理员身份运行。
    
2. 使用以下命令：

``` cmd
mklink /d "目标链接路径" "原始文件夹真实路径"

mklink /d "C:\Users\你的用户名\Desktop\工作资料" "D:\工作资料"
```

**参数说明**

- `/d`：创建**目录符号链接**（支持网络路径、跨分区，但需要管理员权限）
    
- `/j`：创建**目录联接（Junction）**（只支持本地 NTFS 路径，不需要指向网络，某些情况下权限要求宽松，但仍建议管理员运行）


#### win下powershell的 

你可以用 `New-Item` 并指定 `-ItemType SymbolicLink` 来创建目录符号链接

``` powershell
New-Item -ItemType SymbolicLink -Path "D:\test\wxds\.opencode\skills" -Target "E:\mycode\ghj-skills\skills"
```


## 链接目录


### powershell
``` powershell

New-Item -ItemType SymbolicLink -Path "D:\test\wxds\.opencode\skills" -Target "E:\mycode\ghj-skills\skills"

```


### cmd

``` cmd
# 项目级共享到 opencode
mklink /d "D:\test\wxds\.opencode\skills" "E:\mycode\ghj-skills\skills"

# 全局共享到 opencode
mklink /d "D:\test\wxds\.opencode\skills" "E:\mycode\ghj-skills\skills"


```


### mac

``` bash

```

