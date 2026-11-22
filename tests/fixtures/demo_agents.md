# Demo agents

The agents of an invented person, Nour, who runs a small bakery. Nothing here describes a real person, business or
service. The addresses use example.com and the private ranges, which lead nowhere real.

name: Order reminder
does: reminds the counter of tomorrow's orders
runs: this machine
reads: the order list
sends: nowhere
may: draft
ratifies: Nour
owner: Nour
stop: close the reminder app
last_run: 2026-11-19

name: Shop replier
does: answers questions on the shop page
runs: outside (a hosting service)
reads: customer messages; the price list
sends: api.example.com
keys: SHOP_MODEL_KEY
may: send, reply
ratifies: nobody
passes: Weekly totals
last_run: 2026-11-18

- name: Weekly totals
- purpose: adds up the week's orders and posts the sheet
- where: my network (the back-room PC)
- reads: the order list; Corner kiosk sales
- goes to: sheets.example.com
- secrets: SHOP_MODEL_KEY
- can: post
- signed by: Nour
- responsible: Nour
- last run: 2026-06-01

name: Recipe printer
does: prints recipe cards for the Saturday class
runs: 192.168.1.40
reads: recipe cards
sends: this machine
may: print
owner: Nour
passes: Label maker
last_run: 2026-11-15
