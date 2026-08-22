# GPG Signing Guide

How to sign commits for the SF Pride Minutebook.

## Prerequisites

- Git installed
- GPG (GnuPG) installed
- GitHub account with write access to this repository

## Step 1: Generate a GPG Key

```bash
gpg --full-generate-key
```

When prompted:
- **Key type**: RSA and RSA (default)
- **Key size**: 4096 bits
- **Expiration**: 1 year recommended
- **Real name**: Your legal name (as it appears in meeting records)
- **Email**: Your sfpride.org email address
- **Passphrase**: Strong, unique password

## Step 2: Get Your Key ID

```bash
gpg --list-secret-keys --keyid-format=long
```

Output will look like:
```
sec   rsa4096/ABC123DEF4567890 2026-01-16 [SC]
      ABCD1234EFGH5678IJKL9012MNOP3456QRST7890
uid           [ultimate] Your Name <you@sfpride.org>
ssb   rsa4096/XYZ987WVU6543210 2026-01-16 [E]
```

Your key ID is `ABC123DEF4567890` (the part after `rsa4096/`).

## Step 3: Configure Git

```bash
# Set your signing key
git config --global user.signingkey ABC123DEF4567890

# Sign all commits by default
git config --global commit.gpgsign true

# Sign all tags by default
git config --global tag.gpgsign true
```

## Step 4: Add Key to GitHub

1. Export your public key:
   ```bash
   gpg --armor --export ABC123DEF4567890
   ```
2. Copy the output (including `-----BEGIN PGP PUBLIC KEY BLOCK-----`)
3. Go to GitHub → Settings → SSH and GPG keys → New GPG key
4. Paste and save

## Step 5: Making Signed Commits

If you enabled `commit.gpgsign`, commits are signed automatically:
```bash
git commit -m "Add January 2026 board meeting minutes"
```

To sign explicitly:
```bash
git commit -S -m "Add January 2026 board meeting minutes"
```

## Verifying Your Commit Signature

```bash
git log --show-signature -1
```

Look for:
```
gpg: Signature made Fri Jan 16 01:00:00 2026 PST
gpg: Good signature from "Your Name <you@sfpride.org>"
```

## Troubleshooting

### "gpg failed to sign the data"

Tell Git where GPG is:
```bash
# macOS with Homebrew
git config --global gpg.program $(which gpg)

# If using GPG Suite
export GPG_TTY=$(tty)
```

Add to your `~/.zshrc` or `~/.bashrc`:
```bash
export GPG_TTY=$(tty)
```

### Key expired

Generate a new key and update your records in [CONTRIBUTORS.md](CONTRIBUTORS.md).

## Resources

- [GitHub: Signing commits](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits)
- [GPG Manual](https://gnupg.org/documentation/manuals/gnupg/)
