# SF Pride Digital Minutebook

The official, publicly accessible record of San Francisco Pride's board and committee meetings.

## 🎯 Purpose

This repository serves as San Francisco Pride's **digital minutebook**—a transparent, verifiable archive of organizational governance. All meeting minutes are:

- **Public**: Available for anyone to read
- **Verifiable**: Every commit is GPG-signed by an authorized officer
- **Immutable**: Git history provides a tamper-evident audit trail
- **Searchable**: Markdown format enables full-text search

## 🔐 Verifying Authenticity

Every commit in this repository should be signed with a GPG key. To verify:

```bash
# View the signature on the most recent commit
git log --show-signature -1

# Verify all commits are signed
git log --pretty="format:%H %G? %GK %an" --all
```

The `%G?` field shows:
- `G` = Good signature
- `B` = Bad signature
- `U` = Untrusted signature
- `N` = No signature

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for the list of authorized signers and their public keys.

## 📁 Repository Structure

```
minutebook/
├── board/           # Board of Directors meetings
├── committees/      # Committee meetings
├── membership/      # Annual membership meetings
├── resolutions/     # Formal board resolutions
├── elections/       # Election records
└── templates/       # Meeting minute templates
```

## 📋 Disclosure Policy

| Content | Access |
|---------|--------|
| Approved minutes | Public immediately |
| Draft minutes | Public after approval |
| Personnel matters | Summary only |
| Closed session | Not published |

## 🔗 Related Resources

- [SF Pride Bylaws & Policies](https://sfpride.github.io/bylaws)
- [sfpride.org](https://sfpride.org)

## 📬 Records Requests

For records not available in this repository, contact:
- **Email**: secretary@sfpride.org
- **Mail**: SF Pride, 584 Castro Street, Suite 154, San Francisco, CA 94114

---

*San Francisco Pride Celebration Committee, Inc.*
