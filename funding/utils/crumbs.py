from typing import List

from quart import url_for

from funding.models.database import Proposal, ProposalStatus


class Crumb:
    def __init__(self, name, route_name=None, url=None):
        self.route_name = route_name
        self.name = name
        self._url = url

    @property
    def url(self):
        if not self._url:
            return url_for(self.route_name)
        return self._url


crumb_home = Crumb(route_name="bp_routes.root", name="Home")
crumb_ideas = Crumb(route_name="bp_routes.ideas", name="Ideas")
crumb_funding = Crumb(route_name="bp_routes.funding", name="Funding")
crumb_wip = Crumb(route_name="bp_routes.wip", name="Work in Progress")
crumb_completed = Crumb(route_name="bp_routes.completed", name="Completed")

crumb_what = Crumb(route_name="bp_routes.what", name="What is FCS")
crumb_how = Crumb(route_name="bp_routes.how", name="How to submit")
crumb_about = Crumb(route_name="bp_routes.about", name="About")
crumb_disclaimer = Crumb(route_name="bp_proposals.disclaimer", name="Disclaimer")

crumb_proposal_add = Crumb(route_name="bp_proposals.edit", name="Add Proposal")


def proposal_crumbs_base(proposal: Proposal) -> List[Crumb]:
    statuses = {
        ProposalStatus.wip: crumb_wip,
        ProposalStatus.idea: crumb_ideas,
        ProposalStatus.funding_required: crumb_funding,
        ProposalStatus.completed: crumb_completed
    }

    crumbs = [crumb_home]
    if proposal.status in statuses:
        crumbs.append(statuses[proposal.status])
    return crumbs
