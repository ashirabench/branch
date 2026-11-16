BRANCH for openLCA, free and open source (MPL 2.0). BRANCH is an independent project. It is not affiliated with, sponsored by or endorsed by GreenDelta GmbH, the developer of openLCA; "for openLCA" says only which software BRANCH works with. openLCA and the other product names mentioned here belong to their owners.

Version 0.2.0 corrects an error of versions 0.1.1 and 0.1.2, which counted secondary aluminium twice and made the aluminium can and the foil of cartons look better than they are. Please update.

On a Mac, open the .dmg for your chip and drag BRANCH into Applications. The first time, right click the app in Finder and choose Open.
On Windows, run the setup file. If SmartScreen warns you, click More info and then Run anyway.

BRANCH compares two products from their bill of materials (15 materials) or from processes that you choose by name in your openLCA database, and it asks only the questions that can change the answer.

Start openLCA 2, open the BAFU:2026 database and start the IPC server on port 8080 (Tools, then Developer tools, then IPC Server). Then open BRANCH.
The app never ships BAFU factors: it reads them from your own openLCA.
