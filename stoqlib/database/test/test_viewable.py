# -*- coding: utf-8 -*-
# vi:si:et:sw=4:sts=4:ts=4

##
## Copyright (C) 2006 Async Open Source <http://www.async.com.br>
## All rights reserved
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU Lesser General Public License as published by
## the Free Software Foundation; either version 2 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with this program; if not, write to the Free Software
## Foundation, Inc., or visit: http://www.gnu.org/.
##
## Author(s): Stoq Team <stoq-devel@async.com.br>
##

"""Tests for module :class:`stoqlib.database.viewable.DeprecatedViewable`"""

import datetime

from storm.expr import LeftJoin, Sum

from stoqlib.database.viewable import Viewable
from stoqlib.domain.account import AccountTransaction
from stoqlib.domain.commission import Commission
from stoqlib.domain.payment.payment import Payment
from stoqlib.domain.payment.views import OutPaymentView
from stoqlib.domain.person import Person, Client
from stoqlib.domain.sale import Sale
from stoqlib.domain.test.domaintest import DomainTest
from stoqlib.domain.till import TillEntry


class DeprecatedViewableTest(DomainTest):

    def test_sync(self):
        self.clean_domain([AccountTransaction, Commission, TillEntry, Payment])

        # Create a payment
        due_date = datetime.date(2011, 9, 30)
        payment = self.create_payment(payment_type=Payment.TYPE_OUT,
                                      date=due_date)
        # Results should have only one item
        results = list(OutPaymentView.select(store=self.store))
        self.assertEquals(len(results), 1)

        # And the viewable result should be for the same payment (and have same
        # due_date)
        viewable = results[0]
        self.assertEquals(viewable.payment, payment)
        self.assertEquals(viewable.due_date.date(), due_date)

        # Update the payment due date
        new_due_date = datetime.date(2010, 4, 22)
        payment.due_date = new_due_date

        # Before syncing, the due date still have the old value
        self.assertEquals(viewable.due_date.date(), due_date)

        # Sync the viewable object and the due date should update to the new
        # value
        viewable.sync()
        self.assertEquals(viewable.due_date.date(), new_due_date)


class ClientView(Viewable):
    person = Person
    client = Client
    person_name = Person.name
    total_sales = Sum(Sale.total_amount)

    tables = [
        Client,
        LeftJoin(Person, Person.id == Client.person_id),
        LeftJoin(Sale, Sale.client_id == Client.id),
    ]

    group_by = [Person, Client, person_name]


class ViewableTest(DomainTest):

    def test_viewable_with_group_by(self):
        client = self.create_client(name='Fulano')
        sale = self.create_sale(client=client)
        sale.total_amount = 111

        sale = self.create_sale(client=client)
        sale.total_amount = 253

        views = self.store.find(ClientView)
        for view in views:
            if view.client == client:
                break
        else:
            raise AssertionError('client should be found in the view')

        self.assertEquals(view.person, client.person)
        self.assertEquals(view.person_name, 'Fulano')
        self.assertEquals(view.total_sales, 364)
