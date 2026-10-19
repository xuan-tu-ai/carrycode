# Prompts

`tracker.md` and `compiler.md` will hold the system prompts for the runtime roles (milestone M1).

Write them from the ideas in the paper (§3.3, Appendix A). **Do not copy text from the
paper's Appendix D**: the original authors have not published a license.

What each prompt must state:

- **Tracker**
  - Duties: maintain candidates; request compilation only when a coherent carrier version
    exists.
  - The three carrier types, with coding examples.
  - The check specs it may request: `file_exists`, `git_diff_nonempty`, `python_compiles`,
    `test_outcome`.
  - Output: JSON matching `TrackerOutput`.
- **Compiler**
  - Use only the authorized evidence for claims.
  - Keep in the EC only what carriers do not capture.
  - An attempt without a seen outcome is an attempt, not a success.
  - Abstain when the result cannot honestly replace the live tail.
  - Output: JSON matching `CompilerOutput`.
