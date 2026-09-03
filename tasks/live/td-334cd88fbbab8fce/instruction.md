# fix(cwd): Fix exception in case of running command being in removed directory on macOS

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

### Before

macOS:
```xsh
cd /tmp
mkdir dir
cd dir
touch file
# Remove or move /tmp/dir to trash
ls
```
Result:
```xsh
Traceback (most recent call last):                                      
  File                                                                  
"/Users/pc/.local/[redacted-repo]-env/lib/python3.14/site-packages/[redacted-repo]/main.py",
line 1267, in main                                                      
    sys.exit(main_[redacted-repo](args))                                          
             ~~~~~~~~~~^^^^^^                                           
  File                                                                  
"/Users/pc/.local/[redacted-repo]-env/lib/python3.14/site-packages/[redacted-repo]/main.py",
line 1314, in main_[redacted-repo]                                                
    shell.shell.cmdloop()                                               
    ~~~~~~~~~~~~~~~~~~~^^                                               
  File "/Users/pc/.local/[redacted-repo]-env/lib/python3.14/site-packages/[redacted-repo]/sh
ells/ptk_shell/__init__.py", line 561, in cmdloop                       
    line = self.precmd(line)                                            
  File "/Users/pc/.local/[redacted-repo]-env/lib/python3.14/site-packages/[redacted-repo]/sh
ells/base_shell.py", line 375, in precmd                                
    self.precwd = os.getcwd()                                           
                  ~~~~~~~~~^^                                           
PermissionError: [Errno 1] Operation not permitted                      
[redacted-repo] encountered an issue during launch.                               
Please report to [redacted-url]                  
Failback to /bin/zsh                           
```

### After

```xsh
ls
# ls: .: Operation not permitted
# [redacted-repo]: working directory does not exist: /private/tmp/dir
cd ..
```

## For community
⬇️  **Please click the 👍 reaction instead of leaving a `+1` or 👍  comment**

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
