RPi4 Yocto: configure from Windows before first boot
==================================================
1. Flash this image with Raspberry Pi Imager, skip Raspberry Pi OS customization.
2. Reinsert the SD card. Its visible FAT boot volume contains network-config,
   this README and public-key/password examples.
3. Connect the RPi4 Ethernet port to a router providing DHCP. network-config
   already selects eth0 DHCP. To use static IPv4, edit MODE and the example
   address/netmask/gateway/DNS lines. This is KEY=VALUE, NOT cloud-init YAML.
4. In Windows PowerShell, generate an SSH key if you do not already have one:

   ssh-keygen -t ed25519

   Choose a passphrase when prompted. Then replace E: below with the SD FAT
   drive letter (never copy id_ed25519; only its public .pub file):

   Copy-Item "$env:USERPROFILE\.ssh\id_ed25519.pub" 'E:\authorized_keys'

   Do not add a .txt extension to authorized_keys. Eject the card safely.
5. Boot the Pi. Look up its IPv4 in your router DHCP client list, then run:

   ssh root@THE_PI_IPV4

   This works with your private key; no serial cable or preset password is
   needed. Root SSH empty-password logins are disabled. No default public key
   or shared password is installed. If you use a different key filename:

   ssh -i "$env:USERPROFILE\.ssh\YOUR_KEY" root@THE_PI_IPV4

After import, setup-result.txt on the FAT volume reports success/errors.
It contains no private keys or password hashes. A public authorized_keys file
may stay on FAT. Changing it triggers reimport; unchanged files do not overwrite
subsequent on-board edits. network-config behaves the same way.

Optional password login: fill userconf.txt.example using root: followed by a
real SHA-512 crypt hash (openssl passwd -6), remove its comments, then rename
it userconf.txt. Plaintext and placeholder passwords are rejected. A valid
password file is removed after import. SSH public keys are simpler on Windows.

GPIO firmware/pin overlays still belong in config.txt. After SSH login, use
gpioinfo/gpioget/gpioset from libgpiod-tools to inspect/request GPIO lines; check
actual gpiochip/line mapping first. No AP/Wi-Fi stack is included in this image.
Kernel, full DWARF symbols and startup/RCU debugging configuration are unchanged.
