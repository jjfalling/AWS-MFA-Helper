![Dependancy Status](https://pyup.io/repos/github/jjfalling/TOTP-Generator/shield.svg)

# AWS MFA Helper
Automate obtaining MFA (STS) credentials

This utility will request STS credentials from AWS, then update  ~/.aws/credentials with the new credentials. STS credentials are stored in a profile suffixed with -mfa. Then you can switch to the mfa suffexed profile in your AWS client. 

If you have [TOTP Generator](https://github.com/jjfalling/TOTP-Generator) installed this utility will attempt to automate the TOTP code generation (see below).

This utility relies on some custom settings in your AWS config (all are prefixed with helper_). You will need to update your AWS configuration (~/.aws/config) and add the MFA ARN to each profile you want to use this utility with, along with an optional TOTP service name. For example:
```
[profile my-aws-profile]
helper_mfa_serial = arn:aws:iam::123456789012:mfa/your-username
helper_totp_service_name = (Optional: the TOTP service name in TOTP Generatior)
```


You can install this utility with `pip install AWS-MFA-Helper`.

Run with the --help flag for more information.
