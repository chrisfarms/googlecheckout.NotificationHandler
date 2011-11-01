googlecheckout.NotificationHandler
==================================

NotificationHandler is simple base class for implementing the [Google Checkout Notification API (XML v2.5)](http://code.google.com/apis/checkout/developer/Google_Checkout_XML_API_Notification_API.html) with AppEngine's [webapp](http://code.google.com/appengine/docs/python/gettingstarted/usingwebapp.html) framework.

Installing the handler
----------------------

Just copy the file to the root of your application.

Using the handler
-----------------

Create a webapp handler by subclassing the `NotificationHandler` defining a merchant_details 
method and overriding any notification methods you wish to use:

```python    
    class MyNotificationHandler(NotificationHandler)

        def merchant_details():
            "return a tuple of your merchant details"
            return (your_id, your_key)

        def new_order(self):
            logging.info("got a new order notification", self.notification)
```

By default `NotificationHandler` accepts (and acknowledges) all notifications and leaves a 
message in the log. It expects that you will override one or more of the following methods
in your Handler:

```python  
      class MyNotificationHandler(NotificationHandler)
      
          def new_order(self):
              "Do something with the new-order-notification"

          def risk_information(self):
              "Do something with the risk-information-notification"

          def order_state_change(self):
              "Do something with the order-state-change-notification"

          def charge_amount(self):
              "Do something with the charge-amount-notification"
              
          def chargeback_amount(self):
              "Chargeback info..."

          def refund_amount(self):
              "Refund info..."

          def authorization_amount(self):
              "Auth details..."
```

Notification Data
-----------------

Within the context of a NotificationHandler `self.notification` contains a dict-like object
with all the [notification values](http://code.google.com/apis/checkout/developer/Google_Checkout_XML_API_Notification_API.html#Types_of_Notifications) from the request.

The values in self.notifications are pythonized by converting `-` to `_`. So 'order-summary' becomes 'order_summary'
This allows you to access the values via dot-notation. For example:

```python
    self.notification.order_summary.google_order_number # contains the order reference
```

As a convineince the structure for fetch the `items` in the `shopping-cart` elements has been shortend slightly from the XML version. To iterate each item you can do:

```python
    for item in self.notification.shopping_cart.items:
        # item.item_name
        # etc
```

Example
-------

As a full example, if we have a simple Order model to store our new order details
we could then make a notification handler to store the order details

```python
    from google.appengine.ext import webapp,db
    from google.appengine.ext.webapp import util
    from googlecheckout import NotificationHandler
    
    class Order(db.Model):
        amount = db.StringProperty()
        paid = db.StringProperty()
        name = db.StringProperty()
        email = db.StringProperty()
        address_line_1 = db.StringProperty()
        city = db.StringProperty()
        postcode = db.StringProperty()
        phone = db.StringProperty()
        items = db.StringListProperty()

    class CheckoutHandler(NotificationHandler):
        "An example notifcation handle"

        def merchant_details():
            "return a tuple of your merchant details"
            return ("12345678910", "Axoiuyfq2309230f9u2gf")
            
        def new_order(self):
            "Create an order for the incoming order notification"
            # first check if we already created this order (maybe the notification came in twice)
            order = Order.get_by_key_name(self.notification.google_order_number)
            if order:
                return
            # otherwise create an order
            order = Order(
                key_name       = self.notification.google_order_number,
                name           = self.notification.buyer_shipping_address.contact_name,
                email          = self.notification.buyer_shipping_address.email,
                address_line_1 = self.notification.buyer_shipping_address.address1,
                city           = self.notification.buyer_shipping_address.city,
                postcode       = self.notification.buyer_shipping_address.postal_code,
                amount         = self.notification.order_total,
                phone          = self.notification.buyer_shipping_address.phone)
            # record each item in the order
            for item in self.notification.shopping_cart.items:
                order.items.append( item.item_name )
            order.put()

        def charge_amount(self):
            "Mark a previous order as paid"
            order = Order.get_by_key_name(self.notification.google_order_number)
            order.paid = True
            order.put()
    
    def main():
        routes = [
            ('/notifications/checkout', CheckoutHandler)
        ]
        application = webapp.WSGIApplication(routes, debug=True)
        util.run_wsgi_app(application)
    if __name__ == '__main__':
      main()
```

Cancelling/Shipping and Interacting via Order Processing API
------------------------------------------------------------

**[Experimental]** A few of the [Financial Commands](http://code.google.com/apis/checkout/developer/Google_Checkout_XML_API_Financial_Commands.html#Overview) from the [Order Processing API](http://code.google.com/apis/checkout/developer/Google_Checkout_XML_API_Processing.html#order_processing_api) are exposed via the `remote_order` method on the handler. 

`remote_order` returns an instance of googlecheckout.Order for the current order.

For example if you wanted to automatically ship all orders under $10 and instantly cancel all orders over $50 you might do something like:

```python
    class MyNotificationHandler(NotificationHandler):
        "An example notifcation handler"

        def merchant_details():
            "return a tuple of your merchant details"
            return ("12345678910", "Axoiuyfq2309230f9u2gf")
                
        def new_order(self):
            total = float(self.notificaiton.order.total)
            if total < 10:
                self.remote_order.charge_and_ship(self.notificaiton.order_total)
            elif total > 3000:
                self.remote_order.cancel()
```

`remote_order` calls will raise an exception if they fail so you will probably want to wrap them in `try`/`catch` to handle them correctly.

You can use the Order Processing methods without the NotificationHandler by setting up the order class:

```python
    import googlecheckout
    CheckoutOrder = googlecheckout.Client(merchant_id='171973829346743',
        merchant_key='ZyCwRxR5AZrIkOkumZtyVQ', 
        sandbox=True, 
        currency="GBP")

    # init order class with order-number
    order = CheckoutOrder('859558483052501')

    # authorize an order
    order.authorize()

    # charge and ship
    order.charge_and_ship() 

    # refund an order with reason and optional amount
    order.refund("it's all squishy", amount=10)

    # cancel the order
    order.cancel()
```

Notes
-----

Exceptions raised during execution of the notification will result in the notification being resent
from google-checkout.

raise `IgnoreNotification` if you wish to raise an exception and also return send an OK acknowledgement to
google-checkout to prevent re-sending.

Acknowledgements & Author
-------------------------

This code started life in the [chippyshop source](http://code.google.com/p/chippysshop/source/browse/googlecheckout.py) and was refactored/hacked/extended by Chris Farmiloe into this reusable module.
