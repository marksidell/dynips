## Overview

The dynips service provides a way to update a DNS hostname
automatically when the IP address of a client computer changes. We use
dynips at our company to grant firewall access to trusted IPs, for
employees who are mobile or don't have fixed IPs.

The service registers hostnames by defining DNS 'A' records in a
domain that you specify. You must own the domain, and it must be
managed by AWS Route 53. When you configure the service, you specify a
root name within your domain, and all hostnames are defined as
subdomains of that root. For example, if you own `mydomain.com`, you
can specify the root name to be `ips.mydomain.com`. Registered
hostnames will then have names of the form
`hostname.ips.mydomain.com`.

The service supports multiple client accounts, each with its
own username and password. Each client may register and track the IPs
of any number of hostnames. Clients access the service to update IPs
via standard HTTPS GET requests. A client may perform an update manually from a
web browser, or automatically using some form of cron job and tools
like curl.

Normally, the service expires hostnames that clients fail
to update regularly. This ensures that the IP addresses for temporary
locations, such as coffee shops, are automatically expired.
It is also possible for a client to *hold* a
hostname so that it doesn't expire. Holding is useful for clients such
as iPhones, for which at present there is no app to perform automatic
periodic updates.

As a security measure, the service locks IPs and/or users that fail
to provide the correct credentials after a certain number of attempts.

Client accounts are managed via a simple command line utility, written
in Python.

It is possible to associate a custom domain with the service web
address (such as "dynips.mydomain.com"). To use a custom domain,
you must have an appropriate SSL certificate for the domain.

The service is implemented in Python, using AWS Lambda Functions, the
API Gateway, S3, and Route 53. No dedicated web server is required to
run the service.

### Client Usage

#### Overview

In the following section, `<dynip-server>` represents the hostname
used to access your instance of the service. If you don't assign
a custom domain to the service, the hostname will be an AWS-assigned
API gateway address of the form:

    12345678.execute-api.aws-region.amazonaws.com/prod/

If you assign a custom domain, you would define it to be a CNAME to
the API gateway address. It can be any name you choose. For example:

    dynips.mydomain.com

#### Client actions

To determine your current IP, use:

    https://<dynip-server>/dynips

The server will return the following JSON string:

    {"ip": "1.2.3.4"}

To register the IP for a hostname, use:

    https://<dynip-server>/dynips?host=<hostname>&key=<password>

This request associates your browser's current IP with the specified
`<hostname>`. The `<password>` is your assigned password.
The `<hostname>` is of the form:

    <root>[-<extension>]

where `<root>` is your assigned username and `-<extension>` is an optional dash
followed by an alphanumeric extension that you can choose. For
example, if your username is `sally`, you can register the simple
hostname `sally`, but you can also create other names, such as
`sally-laptop` and `sally-iphone`. Users are free to make up as many names as
they need.

By default, the service associates your current browser client IP with the
hostname. But for special situations, you can specify a particular IP
by adding an `ip` argument:

    https://<dynip-server>/dynips?host=<hostname>&key=<password>&ip=<ip-address>

The service will expire a hostname that is not registered at least
once an hour, by default. In some situations you may want to keep a
name alive even when you can't ping the service regularly. For
example, at present there's no way to automatically ping the service
from an iPhone. To keep a name from expiring, add the argument
`expire=no`:

    https://<dynip-server>/dynips?host=<hostname>&key=<password>&expire=no

This causes the hostname to remain valid until you
register the same name without the `expire` argument.

For all registration requests, the server returns a JSON string
of the following form:

    {
      "host":"<FQDN for the registered hostname>",
      "ip":"<the IP address from which the request was made>",
      "action":"updated|no_change",
      "cur_ip":"<the IP of the hostname prior to the call>",
      "new_ip":"<after a change, the new IP of the hostname>"
    }

Finally, you can find out the current IP for a hostname by omitting
the key from a request:

    https://<dynip-server>/dynips?host=<hostname>

The server returns the following JSON string:

    {
      "host":"<FQDN for the hostname>",
      "ip":"<the client IP>",
      "cur_ip":"<the IP currently assigned to the hostname>"
    }

### The Management Command Line Tool

The `dynip` Python program is used to manage user accounts and
hostnames. You can run the program on any computer with Python 2.7
installed.

#### Prerequistes
The program requires the following Python packages:

- **boto3** - The AWS Python API
- **passlib** - A password hashing library
- **pytz** - Timezone definitions

#### AWS Credentials

By default, `dynip` uses the standard mechanisms supported by boto3 to
obtain its AWS credentials. These include searching for configuration
files in places like `~/.aws/credentials`. See the boto3 documentation
for all of the options.

You can also pass credentials to `dynip` via the optional arguments
`--acccess-key-id`, `--secret-access-key`, and `--session-token`.

The section **IAM Roles and Policies**, later in this README, details
the rights required to run `dynip`.

#### Usage

Call `dynip` as follows:

    dynip <command> <--arg1> .. <--argN>

The commands are:

**create**

    dynip create --user=<user> [--key=<key> | --key-length=<len>]

Create a user account. Arguments:

- `--user=<user>` (required) specifies the username. Names must be
alphanumeric strings, and are case-insensitive.

- `--key=<key>` (optional) specifies the user key (i.e. password).
Keys must be at least 9 characters long.

- `--key-length=<len>` (optional) specifies a key length. If this argument is
included, the program generates a random string of the specified
length. The minimum allowed length is 9. The program prints the
generated key.

You can specify a `--key` or `--key-length`, but not both. If you specify
neither, the program generates a 16-character random string and prints
it.

NOTE: The program stores a hash of the key, not the key itself, so it's
your responsibility to record any key the program generates.

**edit**

    dynip edit --user=<user> [--key=<key> | --key-length=<len>]

Edit a user account. The arguments are the same as for **create**.

**delete**

    dynip delete --user=<user>

Delete a user account, and any hostnames associated with it.

**lock**

    dynip lock [--user=<user>] [--ip=<ip>]

Lock a user and/or IP address, to block access to the service.
Arguments:

- `--user=<user>` (optional) specifies a username.
- `--ip=<ip>` (optional) specifies an IP address in the standard form
`n.n.n.n`.

You can specify a user, IP address, or both.

**unlock**

    dynip unlock [--user=<user>|*] [--ip=<ip>|*]

Unlock a user and/or IP address, to grant access to the service. The
arguments are the same as for **lock**. For **unlock**,
you can use the wildcard `*`, to unlock all currently locked users and/or IPs.

**list**

    dynip list

List all registered hostnames, users, and user/IP locks.

**expire**

    dynip expire [--max-age=<seconds>]

Expire all hostnames that have not been updated more recently than the
specified number of seconds ago. If no `--max-age` argument is
specified, the default maximum age is used. The default is 3600
seconds, but you can change it when you configure the
service.

### Hostname Expiration

In order to expire hostnames automatically, an expirer daemon must be
run periodically. There are a couple of ways to run an expirer:

#### A Lambda Function

By default, the dynips installation program creates a
`dynips-expirer` lambda function, which when run expires all
out-of-date hostnames. There are various ways you could
arrange to run the lambda periodically. The best method
is with a lambda "Scheduled Event" source.
Unfortunately, the only way at
present to create a scheduled event is via the AWS console. To
schedule the `dynips-expirer` do this:

1. Install dynips
2. In the AWS Console, find the `dynips-expirer` lambda service and
click it.
3. On the lambda's **Event sources** tab, click **Add event source**.
4. On the **Add event source** dialog, select event source type
**Scheduled Event** and fill in the rest of the fields to create a
schedule.

#### A cron job

You can also create a cron job on a convenient computer to run the
command `dynip expire` periodically. Of course, the job must have
access to the necessary AWS credentials.

### Installation

The dynips installer uses the standard sequence of commands:

    python configure [options]
    make
    sudo make install

The `configure` program has several required options and a plethora of
optional ones, as follows:

#### Required Options

`--zone-id=<id>` is the ID of the Route 53 zone used to manage the
domain in which hostnames are registered. The zone must already exist.

`--domain-root=<name>` is the root domain name to be used for
hostnames. The FQDN for a hostname is `<hostname>.<domain-root>`
The domain root must be a valid name for the Route 53 zone you are
using. For example, if your zone has the root name
`mydomain.com`, you can specify a domain root of `mydomain.com` or a
subdomain such as `ips.mydomain.com`. In general, it's best to define
a subdomain so that registered hostnames don't collide with other
names you may define for the zone.

`--s3-bucket=<bucket>` is the name of the S3 bucket to be used to
store dynips user account information and the states of registered
hostnames. If the bucket doesn't exist, the installer will create it.

#### Optional Options

`--default-ip-<ip>` is the IP address to be assigned to expired
hostnames. The default is `10.10.10.10`.

`--ttl=<seconds>` is the DNS TTL assigned to hostnames. The default is
10 seconds. Normally, it's best to have a short TTL so that hostname
IP changes propogate quickly.

`--max-age=<seconds>` is the hostname expiry age. The default is 3600
seconds.

`--max-errors=<count>` is the max number of login errors permitted for
a given user or client IP address. When this number of errors is
reached, the user and/or IP is locked out. The default is 5 errors.

`--pw-hash-rounds=<count>` is the number of hash rounds to perform
when generating user account password hashes. The default is 8000
rounds. (The hash function is PBKDF2 SHA256.)

`--server-lambda-name=<name>` is the name assigned to the server
lambda function and its API gateway. The default is `dynips-server`. Normally you
shouldn't need to change this name unless you already have a lambda
function with that name.

`--expirer-lambda-name=<name>` is the name assigned to the expirer
lambda function. The default is `dynips-expirer`.

`--server-iam-role=<name>` is the name of the IAM role used by the
server lambda function. The default is the same name assigned to the
server lambda function (which by default is `dynips-server`). You can
assign a different name if you already have an IAM role with the same
name, or if you want to use a pre-existing IAM role.

`--expirer-iam-role=<name>` is the name of the IAM role used by the
expirer lambda function. The default is the same name assigned to the
expirer lambda function (which by default is `dynips-expirer`). You can
assign a different name if you already have an IAM role with the same
name, or if you want to use a pre-existing IAM role.

`--prefix=<path>` is the installation root dir for the `dynip` program. The default is
`/usr/local`.

`--bindir=<path>` is the installation directory for the `dynip`
program. The default is `$(prefix)/bin`.

`--srcdir=<path>` is the location of the installation source files.
The default is `./` (which means you intend to run make from the same
directory containing the source files).

`--without-bin` causes the  `dynip` program and the `dynips` Python
package, which it uses, not to be installed on the local computer.

`--without-expirer-lambda` causes the expirer lambda function and its
IAM role not to be installed.

`--without-iam-roles` causes no IAM roles to be created. This option
presumes you have already defined IAM roles for the server and expirer
lambda functions.

`--with-server-domain-name` causes a custom domain name to be
associated with the server lambda API gateway. See the following
section.

#### Defining a Custom Domain Name

By specifying the configuration option `--with-server-domain`, you can
cause the installer to associate a domain name with the server API.
This allows you to define a friendlier name for the service URL.
Note that the domain name used here doesn't necessarily have to be
in the same domain as the hostnames domain root.

To define a custom domain name:

- The name you choose must be one you can configure to be a CNAME
pointing to the name assigned to the server API by AWS.
- You must own an SSL certificate that is associated with the domain
name. Also, the certificate key, cert, and chain files
must be resident on the computer where you install dynips.

To configure a custom domain name, use these options:

`--with-server-domain-name`

`--server-domain-name=<name>` is the domain name you wish to use (e.g.
`dynips.mydomain.com`).

`--certificate-file=<path>` is the path to a file containing an SSL
certificate for the domain name.

`--private-key-file=<path>` is the path to a file containing the
certificate's private key.

`--chain-file=<path>` is the path to a file containing the chain to
the root certificate of the authority that issued the certificate.

All of the certificate files must be in PEM format. Of course, once
you have installed dynips you can remove them from the computer.

The installer writes file `server_api.txt`, which contains the
hostname assigned to the server API by AWS, and the full URL used to
access the service. To associate your custom domain name with the
server API hostname, define a CNAME that points your domain name server
to the API hostname. For example, if the API hostname is:

    12345678.execute-api.us-east-1.amazonaws.com

and your domain name is:

    dynips.mydomain.com

then define this CNAME:

    dynips.mydomain.com CNAME 12345678.execute-api.us-east-1.amazonaws.com 

After you define the CNAME, the URL clients will use to access the service is:

    https://dynips.mydomain.com/dynips

### IAM Roles and Policies

By default, the installer creates IAM roles with the correct rights
for the server and expirer. To run the `dynip` command line program,
you must arrange that an IAM user or role be in place with the
necessary rights. Note that if you use a cron job to run the `dynip
expire` operation, the job only needs *Expirer* rights.

The following table summarizes the IAM rights required by the various
dynips processes.

| Rights | Server | Expirer | dynip utility
|--------|--------|---------|------
| Full access to S3 state files, change Route 53 record sets | Yes | Yes | Yes
| Read-only access to S3 user files | Yes | |
| Full access to S3 user files | | | Yes
| Write CloudWatch logs | Yes | Yes |

Below are example policy statements for the rights described in the
table.

#### Full access to S3 state files, change Route 53 record sets 

    {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:ListBucket"
               ],
               "Resource": [
                   "arn:aws:s3:::<dynips-bucket>"
               ]
           },
           {
               "Effect": "Allow",
               "Action": [
                   "s3:PutObject",
                   "s3:GetObject",
                   "s3:DeleteObject"
               ],
               "Resource": [
                   "arn:aws:s3:::<dynips-bucket>/state/*"
               ]
           },
           {
               "Effect": "Allow",
               "Action": [
                   "route53:ChangeResourceRecordSets"
               ],
               "Resource": [
                   "arn:aws:route53:::hostedzone/<dynips-zone>"
               ]
           },
           {
               "Effect": "Allow",
               "Action": [
                   "route53:GetChange"
               ],
               "Resource": [
                   "arn:aws:route53:::change/*"
               ]
           }
       ]
    }

#### Read-only access to S3 user files

    {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:GetObject"
               ],
               "Resource": [
                   "arn:aws:s3:::<dynips-bucket>/users/*"
               ]
           },
       ]
    }

#### Full access to S3 user files

    {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:PutObject",
                   "s3:GetObject",
                   "s3:DeleteObject"
               ],
               "Resource": [
                   "arn:aws:s3:::<dynips-bucket>/users/*"
               ]
           },
       ]
    }

#### Write CloudWatch logs

    {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "logs:CreateLogGroup",
                   "logs:CreateLogStream",
                   "logs:PutLogEvents"
               ],
               "Resource": "arn:aws:logs:*:*:*"
           },
       ]
    }

#### Lambda Function Trust Relationship

In addition to the policies described above, the following trust relationship must be defined,
to allow the AWS lambda service to assume an IAM role:

    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "",
          "Effect": "Allow",
          "Principal": {
            "Service": "lambda.amazonaws.com"
          },
          "Action": "sts:AssumeRole"
        }
      ]
    }

#### AWS Items Installed

The installer creates the following AWS items:

- An S3 bucket, with the name specified by the configuration options.

- An IAM role for the server lambda function, with the default name
`dynips-server`.

- An IAM role for the expirer lambda function, with the default name
`dynips-server`.

- A lambda function for the server, with the default name
`dynips-server`.

- A lambda function for the expirer, with the default name
`dynips-expirer`.

- An API gateway for the server, with the default name
`dynips-server`.

- An optional custom domain name for the server API
gateway.


### How It Works

The hostname registration web service is implemented as a lambda
function. A API gateway attached to the function makes it possible for
external clients to access the service via HTTPS. The service
maintains hostname to IP mappings by updating record sets in a Route 53 zone.

User credentials and hostname state information are stored in an S3
bucket. The bucket is partitioned into *state* and *user* folders, so
that the lambda function can be granted full access to the state
files, but read-only acccess to the user credential files.

All file content is stored as JSON strings.

#### User Files

User files have names of the form:

    <bucket>:users/<username>

A user file contains the following JSON content:

    {
      "user":"<username>",
      "keyhash":"<hash>"
    }

The `<hash>` is a PBBKDF2/SHA256 hash of the user's key. The hash
string includes a prefix that names the hash used and the number of
rounds. This makes it possible for implementations to change the hash
and/or rounds while maintaining backward compatibility with existing
keys. All of this complexity is handled automatically by the passlib
Python package.

#### State Files

State files have names of the form:

    <bucket>:state/<name>.<ext>

A file `<name>` can be a hostname, a username, or an IP address. The
`<ext>` specifies the file type, as follows:

`<hostname>.ping`

A *ping* file records the most-recent registration of a hostname, for
hostnames that have not expired. The file contains the following JSON content:

    { "ip":"<IP-address>" }

`<hostname>.hold`

The presence of a *hold* file indicates that hostname should not be
expired. The file contains the same content as the *ping* file that
was created when the *hold* file was created.

`<hostname>.expired`

The presence of an *expired* file indicates that a hostname has expired.
The file contains the content of the last *ping* file before the
hostname was expired.

`<name>.error.<count>`

Each time a client performs an operation that results in an error
(such as providing invalid credentials), the service writes an *error*
file, where `<name>` is the client IP address. If the error
involves a username, the server also writhes an *error* file where
`<name>` is the username. The `<count>` is an ordinal, starting with
1, that increases each time the server writes a new *error* file for the
same IP and/or username.

`<name>.lock`

When the number of *error* files for a given IP or username reaches a
fixed threshold, the server writes a *lock* file, and thereafter stops
writing corresponding *error* files.  The presences of a *lock* file
causes the server to refuse acccess to the IP or user.

#### Registering a Hostname

The server handles a registration request as follows:

1. If the request is from a client IP for which a *lock* file exists,
or if a *lock* file exists for the username provided by the request,
the server refuses the request.

1. The server validates the request by extracting the username prefix
from the supplied hostname and matching the supplied key with the hash
stored in the user credentials file. If the request is invalid, the
server creates *error* and/or *lock* files, as described previously.

1. For valid requests, the server creates or updates a *ping* file for the requested
hostname. If a corresponding *expired* file exists, the server deletes
it. If the request includes the `expire=no` param, the server creates
a *hold* file for the hostname, if one does not already exist.
Otherwise, if a *hold* file exists, the server deletes it.

1. The server updates the hostname's IP address in the Route 53 zone.

#### Expiring Hostnames

The expirer daemon expires hostnames by enumerating all *ping* files
with a last-modified time older than the specified maximum age, and
for which no *hold* file exists. For each hostname to be expired, the
server creates an *expired* file and deletes the *ping* file. The
expirer also sets the hostname's Route 53 IP address to the *expired* value,
which by default is 10.10.10.10.
