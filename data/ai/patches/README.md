# Patch manifests

When direct canonical mutation is risky or repeatedly fails, agents may create a patch manifest here.

Required fields:
- patch_id
- agent
- target
- base_sha
- change_type
- reason
- dependencies
- tests
- rollback
- status

The canonical writer validates the manifest before applying it. A manifest never bypasses platform safety policy.
